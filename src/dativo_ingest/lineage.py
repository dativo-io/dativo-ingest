"""Data lineage tracking for end-to-end observability."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .config import AssetDefinition
from .logging import get_logger


class LineageNode:
    """Represents a node in the data lineage graph."""

    def __init__(
        self,
        node_id: str,
        node_type: str,
        name: str,
        version: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize lineage node.

        Args:
            node_id: Unique identifier for the node
            node_type: Type of node (source, asset, transformation, target)
            name: Human-readable name
            version: Version of the node (for contracts)
            metadata: Additional metadata
        """
        self.node_id = node_id
        self.node_type = node_type
        self.name = name
        self.version = version
        self.metadata = metadata or {}
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "name": self.name,
            "version": self.version,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class LineageEdge:
    """Represents an edge (relationship) in the lineage graph."""

    def __init__(
        self,
        from_node_id: str,
        to_node_id: str,
        edge_type: str = "derives_from",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize lineage edge.

        Args:
            from_node_id: Source node ID
            to_node_id: Target node ID
            edge_type: Type of relationship (derives_from, transforms, writes_to)
            metadata: Additional metadata
        """
        self.from_node_id = from_node_id
        self.to_node_id = to_node_id
        self.edge_type = edge_type
        self.metadata = metadata or {}
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "edge_type": self.edge_type,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class LineageTracker:
    """Tracks data lineage across ingestion pipeline."""

    def __init__(self, lineage_dir: Optional[Path] = None):
        """Initialize lineage tracker.

        Args:
            lineage_dir: Directory to store lineage metadata (default: /.lineage)
        """
        self.lineage_dir = lineage_dir or Path("/.lineage")
        self.logger = get_logger()
        self.nodes: Dict[str, LineageNode] = {}
        self.edges: List[LineageEdge] = []
        self.run_id = str(uuid4())

    def add_source_node(
        self,
        source_type: str,
        object_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LineageNode:
        """Add source node to lineage graph.

        Args:
            source_type: Type of source (e.g., 'stripe', 'postgres')
            object_name: Name of source object
            metadata: Additional metadata

        Returns:
            Created LineageNode
        """
        node_id = f"source://{source_type}/{object_name}"
        node = LineageNode(
            node_id=node_id,
            node_type="source",
            name=f"{source_type}.{object_name}",
            metadata=metadata or {},
        )
        self.nodes[node_id] = node
        
        self.logger.debug(
            f"Lineage: Added source node {node_id}",
            extra={"event_type": "lineage_node_added", "node_type": "source"},
        )
        
        return node

    def add_asset_node(
        self,
        asset: AssetDefinition,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LineageNode:
        """Add asset contract node to lineage graph.

        Args:
            asset: Asset definition
            metadata: Additional metadata

        Returns:
            Created LineageNode
        """
        node_id = f"asset://{asset.source_type}/{asset.object}@{asset.version}"
        
        asset_metadata = {
            "contract_id": asset.id,
            "owner": asset.team.owner if asset.team else "unknown",
            "classification": (
                asset.compliance.classification
                if asset.compliance and asset.compliance.classification
                else []
            ),
        }
        if metadata:
            asset_metadata.update(metadata)
        
        node = LineageNode(
            node_id=node_id,
            node_type="asset",
            name=asset.name,
            version=asset.version,
            metadata=asset_metadata,
        )
        self.nodes[node_id] = node
        
        self.logger.debug(
            f"Lineage: Added asset node {node_id}",
            extra={"event_type": "lineage_node_added", "node_type": "asset"},
        )
        
        return node

    def add_transformation_node(
        self,
        transformation_name: str,
        transformation_type: str = "schema_validation",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LineageNode:
        """Add transformation node to lineage graph.

        Args:
            transformation_name: Name of transformation
            transformation_type: Type of transformation
            metadata: Additional metadata

        Returns:
            Created LineageNode
        """
        node_id = f"transform://{transformation_type}/{transformation_name}"
        node = LineageNode(
            node_id=node_id,
            node_type="transformation",
            name=transformation_name,
            metadata=metadata or {"transformation_type": transformation_type},
        )
        self.nodes[node_id] = node
        
        self.logger.debug(
            f"Lineage: Added transformation node {node_id}",
            extra={"event_type": "lineage_node_added", "node_type": "transformation"},
        )
        
        return node

    def add_target_node(
        self,
        target_type: str,
        catalog: str,
        table_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LineageNode:
        """Add target node to lineage graph.

        Args:
            target_type: Type of target (e.g., 'iceberg', 'parquet')
            catalog: Catalog name
            table_name: Table name
            metadata: Additional metadata

        Returns:
            Created LineageNode
        """
        node_id = f"target://{target_type}/{catalog}/{table_name}"
        node = LineageNode(
            node_id=node_id,
            node_type="target",
            name=f"{catalog}.{table_name}",
            metadata=metadata or {},
        )
        self.nodes[node_id] = node
        
        self.logger.debug(
            f"Lineage: Added target node {node_id}",
            extra={"event_type": "lineage_node_added", "node_type": "target"},
        )
        
        return node

    def add_edge(
        self,
        from_node: LineageNode,
        to_node: LineageNode,
        edge_type: str = "derives_from",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> LineageEdge:
        """Add edge between lineage nodes.

        Args:
            from_node: Source node
            to_node: Target node
            edge_type: Type of edge
            metadata: Additional metadata

        Returns:
            Created LineageEdge
        """
        edge = LineageEdge(
            from_node_id=from_node.node_id,
            to_node_id=to_node.node_id,
            edge_type=edge_type,
            metadata=metadata or {},
        )
        self.edges.append(edge)
        
        self.logger.debug(
            f"Lineage: Added edge {from_node.node_id} -> {to_node.node_id}",
            extra={"event_type": "lineage_edge_added", "edge_type": edge_type},
        )
        
        return edge

    def record_run(
        self,
        tenant_id: str,
        job_name: str,
        status: str,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record lineage for a complete run.

        Args:
            tenant_id: Tenant identifier
            job_name: Job name
            status: Run status (success, failure)
            metrics: Run metrics

        Returns:
            Lineage record dictionary
        """
        lineage_record = {
            "run_id": self.run_id,
            "tenant_id": tenant_id,
            "job_name": job_name,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges],
            "metrics": metrics or {},
        }
        
        # Save lineage record
        self._save_lineage_record(tenant_id, job_name, lineage_record)
        
        self.logger.info(
            f"Lineage recorded: {len(self.nodes)} nodes, {len(self.edges)} edges",
            extra={
                "event_type": "lineage_recorded",
                "run_id": self.run_id,
                "nodes_count": len(self.nodes),
                "edges_count": len(self.edges),
            },
        )
        
        return lineage_record

    def _save_lineage_record(
        self, tenant_id: str, job_name: str, lineage_record: Dict[str, Any]
    ) -> Path:
        """Save lineage record to disk.

        Args:
            tenant_id: Tenant identifier
            job_name: Job name
            lineage_record: Lineage record dictionary

        Returns:
            Path to saved lineage file
        """
        # Create directory structure
        tenant_dir = self.lineage_dir / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        
        # Save with timestamp-based filename
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{job_name}_{timestamp}_{self.run_id[:8]}.json"
        file_path = tenant_dir / filename
        
        with open(file_path, "w") as f:
            json.dump(lineage_record, f, indent=2)
        
        self.logger.debug(
            f"Lineage saved: {file_path}",
            extra={"event_type": "lineage_saved"},
        )
        
        return file_path

    def get_upstream_lineage(
        self, node_id: str, max_depth: int = 10
    ) -> List[Dict[str, Any]]:
        """Get upstream lineage for a node.

        Args:
            node_id: Node identifier
            max_depth: Maximum depth to traverse

        Returns:
            List of upstream nodes with relationships
        """
        upstream = []
        visited = set()
        
        def traverse(current_id: str, depth: int) -> None:
            if depth >= max_depth or current_id in visited:
                return
            
            visited.add(current_id)
            
            # Find edges pointing to current node
            for edge in self.edges:
                if edge.to_node_id == current_id:
                    from_node = self.nodes.get(edge.from_node_id)
                    if from_node:
                        upstream.append({
                            "node": from_node.to_dict(),
                            "edge": edge.to_dict(),
                            "depth": depth,
                        })
                        traverse(edge.from_node_id, depth + 1)
        
        traverse(node_id, 0)
        return upstream

    def get_downstream_lineage(
        self, node_id: str, max_depth: int = 10
    ) -> List[Dict[str, Any]]:
        """Get downstream lineage for a node.

        Args:
            node_id: Node identifier
            max_depth: Maximum depth to traverse

        Returns:
            List of downstream nodes with relationships
        """
        downstream = []
        visited = set()
        
        def traverse(current_id: str, depth: int) -> None:
            if depth >= max_depth or current_id in visited:
                return
            
            visited.add(current_id)
            
            # Find edges starting from current node
            for edge in self.edges:
                if edge.from_node_id == current_id:
                    to_node = self.nodes.get(edge.to_node_id)
                    if to_node:
                        downstream.append({
                            "node": to_node.to_dict(),
                            "edge": edge.to_dict(),
                            "depth": depth,
                        })
                        traverse(edge.to_node_id, depth + 1)
        
        traverse(node_id, 0)
        return downstream

    def export_to_openlineage(self) -> Dict[str, Any]:
        """Export lineage to OpenLineage format.

        Returns:
            OpenLineage-compatible lineage event
        """
        # Map to OpenLineage format
        # https://openlineage.io/docs/spec/object-model
        
        inputs = []
        outputs = []
        
        for node in self.nodes.values():
            if node.node_type == "source":
                inputs.append({
                    "namespace": node.metadata.get("namespace", "default"),
                    "name": node.name,
                })
            elif node.node_type == "target":
                outputs.append({
                    "namespace": node.metadata.get("namespace", "default"),
                    "name": node.name,
                })
        
        return {
            "eventType": "COMPLETE",
            "eventTime": datetime.now(timezone.utc).isoformat(),
            "run": {
                "runId": self.run_id,
            },
            "job": {
                "namespace": "dativo-ingest",
                "name": "data-ingestion",
            },
            "inputs": inputs,
            "outputs": outputs,
        }
