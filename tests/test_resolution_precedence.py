"""Tests for resolution precedence helper function."""

import pytest

from src.dativo_ingest.registry import resolve_image_and_version


class TestResolutionPrecedence:
    """Test exact precedence order for image and version resolution."""

    def test_job_override_wins_over_everything(self):
        """Job override must win over catalog and registry defaults."""
        image, version = resolve_image_and_version(
            job_image="job/image:1.0",
            job_version="1.0",
            catalog_image="catalog/image:2.0",
            catalog_version="2.0",
            registry_image_default="registry/image:3.0",
            registry_version_default="3.0",
        )
        assert image == "job/image:1.0"
        assert version == "1.0"

    def test_catalog_wins_over_registry_defaults(self):
        """Catalog values must win over registry defaults when no job override."""
        image, version = resolve_image_and_version(
            catalog_image="catalog/image:2.0",
            catalog_version="2.0",
            registry_image_default="registry/image:3.0",
            registry_version_default="3.0",
        )
        assert image == "catalog/image:2.0"
        assert version == "2.0"

    def test_registry_defaults_used_when_catalog_missing(self):
        """Registry defaults must be used when catalog is missing."""
        image, version = resolve_image_and_version(
            registry_image_default="registry/image:3.0",
            registry_version_default="3.0",
        )
        assert image == "registry/image:3.0"
        assert version == "3.0"

    def test_none_when_nothing_provided(self):
        """Must return None when no values provided."""
        image, version = resolve_image_and_version()
        assert image is None
        assert version is None

    def test_partial_job_override(self):
        """Job override for image only, version from catalog."""
        image, version = resolve_image_and_version(
            job_image="job/image:1.0",
            catalog_version="2.0",
            registry_version_default="3.0",
        )
        assert image == "job/image:1.0"
        assert version == "2.0"

    def test_partial_catalog_override(self):
        """Catalog image only, version from registry."""
        image, version = resolve_image_and_version(
            catalog_image="catalog/image:2.0",
            registry_version_default="3.0",
        )
        assert image == "catalog/image:2.0"
        assert version == "3.0"

    def test_job_override_none_overrides_catalog(self):
        """Explicit None in job override should not override (use catalog/registry)."""
        # Note: This tests current behavior - None values are treated as "not provided"
        # If job explicitly sets None, it's still treated as missing
        image, version = resolve_image_and_version(
            job_image=None,  # Treated as not provided
            catalog_image="catalog/image:2.0",
            registry_image_default="registry/image:3.0",
        )
        assert image == "catalog/image:2.0"
        assert version is None

    def test_empty_strings_treated_as_none(self):
        """Empty strings should be treated as None (not provided)."""
        # Empty strings are falsy, so they'll be treated as None
        image, version = resolve_image_and_version(
            job_image="",  # Empty string
            catalog_image="catalog/image:2.0",
            registry_image_default="registry/image:3.0",
        )
        # Empty string is falsy, so catalog wins
        assert image == "catalog/image:2.0"
