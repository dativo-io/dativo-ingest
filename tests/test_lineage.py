"""Tests for lineage tracking."""

import tempfile
from pathlib import Path

import pytest

from dativo_ingest.config import AssetDefinition
from dativo_ingest.lineage import LineageEdge, LineageNode, LineageTracker


@pytest.fixture
def temp_lineage_dir():
    """Create temporary lineage directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_asset():
    """Create sample asset definition."""
    return AssetDefinition(
        id="test-asset-123",
        name="test_customers",
        version="1.0.0",
        status="active",
        source_type="stripe",
        object="customers",
        team={"owner": "data-team@example.com"},
        schema=[
            {"name": "id", "type": "string", "required": True},
        ],
    )


def test_lineage_node_creation():
    """Test creating a lineage node."""
    node = LineageNode(
        node_id="source://stripe/customers",
        node_type="source",
        name="stripe.customers",
        version="1.0.0",
    )
    
    assert node.node_id == "source://stripe/customers"
    assert node.node_type == "source"
    assert node.name == "stripe.customers"
    assert node.version == "1.0.0"


def test_lineage_node_to_dict():
    """Test converting lineage node to dict."""
    node = LineageNode(
        node_id="test-id",
        node_type="source",
        name="test",
    )
    
    node_dict = node.to_dict()
    
    assert node_dict["node_id"] == "test-id"
    assert node_dict["node_type"] == "source"
    assert "timestamp" in node_dict


def test_lineage_edge_creation():
    """Test creating a lineage edge."""
    edge = LineageEdge(
        from_node_id="source://stripe/customers",
        to_node_id="asset://stripe/customers@1.0.0",
        edge_type="derives_from",
    )
    
    assert edge.from_node_id == "source://stripe/customers"
    assert edge.to_node_id == "asset://stripe/customers@1.0.0"
    assert edge.edge_type == "derives_from"


def test_lineage_tracker_initialization(temp_lineage_dir):
    """Test lineage tracker initialization."""
    tracker = LineageTracker(lineage_dir=temp_lineage_dir)
    
    assert tracker.lineage_dir == temp_lineage_dir
    assert len(tracker.nodes) == 0
    assert len(tracker.edges) == 0


def test_add_source_node(temp_lineage_dir):
    """Test adding source node."""
    tracker = LineageTracker(lineage_dir=temp_lineage_dir)
    
    node = tracker.add_source_node(
        source_type="stripe",
        object_name="customers",
    )
    
    assert node.node_type == "source"
    assert node.name == "stripe.customers"
    assert len(tracker.nodes) == 1


def test_add_asset_node(temp_lineage_dir, sample_asset):
    """Test adding asset node."""
    tracker = LineageTracker(lineage_dir=temp_lineage_dir)
    
    node = tracker.add_asset_node(sample_asset)
    
    assert node.node_type == "asset"
    assert node.version == "1.0.0"
    assert len(tracker.nodes) == 1


def test_add_transformation_node(temp_lineage_dir):
    """Test adding transformation node."""
    tracker = LineageTracker(lineage_dir=temp_lineage_dir)
    
    node = tracker.add_transformation_node(
        transformation_name="schema_validation",
        transformation_type="validation",
    )
    
    assert node.node_type == "transformation"
    assert len(tracker.nodes) == 1


def test_add_target_node(temp_lineage_dir):
    """Test adding target node."""
    tracker = LineageTracker(lineage_dir=temp_lineage_dir)
    
    node = tracker.add_target_node(
        target_type="iceberg",
        catalog="bronze",
        table_name="customers",
    )
    
    assert node.node_type == "target"
    assert node.name == "bronze.customers"
    assert len(tracker.nodes) == 1


def test_add_edge(temp_lineage_dir):
    """Test adding edge between nodes."""
    tracker = LineageTracker(lineage_dir=temp_lineage_dir)
    
    node1 = tracker.add_source_node("stripe", "customers")
    node2 = tracker.add_asset_node(AssetDefinition(
        id="test",
        name="test",
        version="1.0.0",
        status="active",
        source_type="stripe",
        object="customers",
        team={"owner": "test@example.com"},
        schema=[{"name": "id", "type": "string"}],
    ))
    
    edge = tracker.add_edge(node1, node2, edge_type="derives_from")
    
    assert edge.from_node_id == node1.node_id
    assert edge.to_node_id == node2.node_id
    assert len(tracker.edges) == 1


def test_record_run(temp_lineage_dir):
    """Test recording a complete run."""
    tracker = LineageTracker(lineage_dir=temp_lineage_dir)
    
    # Add nodes
    tracker.add_source_node("stripe", "customers")
    tracker.add_target_node("iceberg", "bronze", "customers")
    
    # Record run
    lineage_record = tracker.record_run(
        tenant_id="test-tenant",
        job_name="test-job",
        status="success",
    )
    
    assert lineage_record["tenant_id"] == "test-tenant"
    assert lineage_record["job_name"] == "test-job"
    assert lineage_record["status"] == "success"
    assert len(lineage_record["nodes"]) == 2


def test_get_upstream_lineage(temp_lineage_dir, sample_asset):
    """Test getting upstream lineage."""
    tracker = LineageTracker(lineage_dir=temp_lineage_dir)
    
    # Build lineage graph
    source = tracker.add_source_node("stripe", "customers")
    asset = tracker.add_asset_node(sample_asset)
    target = tracker.add_target_node("iceberg", "bronze", "customers")
    
    tracker.add_edge(source, asset)
    tracker.add_edge(asset, target)
    
    # Get upstream lineage for target
    upstream = tracker.get_upstream_lineage(target.node_id)
    
    assert len(upstream) >= 1


def test_get_downstream_lineage(temp_lineage_dir, sample_asset):
    """Test getting downstream lineage."""
    tracker = LineageTracker(lineage_dir=temp_lineage_dir)
    
    # Build lineage graph
    source = tracker.add_source_node("stripe", "customers")
    asset = tracker.add_asset_node(sample_asset)
    target = tracker.add_target_node("iceberg", "bronze", "customers")
    
    tracker.add_edge(source, asset)
    tracker.add_edge(asset, target)
    
    # Get downstream lineage for source
    downstream = tracker.get_downstream_lineage(source.node_id)
    
    assert len(downstream) >= 1


def test_export_to_openlineage(temp_lineage_dir):
    """Test exporting to OpenLineage format."""
    tracker = LineageTracker(lineage_dir=temp_lineage_dir)
    
    tracker.add_source_node("stripe", "customers")
    tracker.add_target_node("iceberg", "bronze", "customers")
    
    openlineage_event = tracker.export_to_openlineage()
    
    assert "eventType" in openlineage_event
    assert "run" in openlineage_event
    assert "job" in openlineage_event
    assert "inputs" in openlineage_event
    assert "outputs" in openlineage_event
