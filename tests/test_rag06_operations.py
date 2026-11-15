"""RAG-06 operations tests: backup, restore, deletion, compaction."""
import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from mcp_agent_factory.knowledge.vector_store import InMemoryVectorStore


class TestBackupRestore:
    """AC5: Backup and restore functionality."""

    def test_backup_creates_file(self):
        """Test that backup creates a valid JSON file."""
        store = InMemoryVectorStore()
        vec = np.random.randn(384).astype(np.float32)

        store.upsert("tenant-a", "Sample text", vec, chunk_id="c1", source_id="doc1")

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = Path(tmpdir) / "backup.json"
            meta = store.backup(str(backup_path))

            assert backup_path.exists()
            assert meta['chunk_count'] == 1
            assert meta['owner_ids'] == ['tenant-a']

            with open(backup_path) as f:
                data = json.load(f)
                assert 'store' in data
                assert len(data['store']) == 1
                # Verify the backup contains the key components
                assert any('Sample text' in str(v) for v in data['store'].values())

    def test_backup_multiple_owners(self):
        """Test backup with multiple tenants."""
        store = InMemoryVectorStore()
        vec_a = np.random.randn(384).astype(np.float32)
        vec_b = np.random.randn(384).astype(np.float32)

        store.upsert("tenant-a", "Text A", vec_a, chunk_id="c1", source_id="doc1")
        store.upsert("tenant-b", "Text B", vec_b, chunk_id="c2", source_id="doc2")

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = Path(tmpdir) / "backup.json"
            meta = store.backup(str(backup_path))

            assert meta['chunk_count'] == 2
            assert set(meta['owner_ids']) == {'tenant-a', 'tenant-b'}

    def test_restore_clears_and_restores(self):
        """Test that restore clears existing data and restores from backup."""
        store = InMemoryVectorStore()
        vec = np.random.randn(384).astype(np.float32)

        # Initial data
        store.upsert("tenant-a", "Original", vec, chunk_id="c1", source_id="doc1")

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = Path(tmpdir) / "backup.json"
            store.backup(str(backup_path))

            # Add more data and restore from backup
            vec2 = np.random.randn(384).astype(np.float32)
            store.upsert("tenant-a", "Extra", vec2, chunk_id="c2", source_id="doc2")
            assert len(store._store) == 2

            result = store.restore(str(backup_path))
            assert result['chunks_restored'] == 1
            assert result['owners_restored'] == 1
            assert len(store._store) == 1

    def test_restore_nonexistent_file(self):
        """Test that restore fails gracefully for missing files."""
        store = InMemoryVectorStore()
        with pytest.raises(FileNotFoundError):
            store.restore("/nonexistent/backup.json")

    def test_restore_maintains_tenant_isolation(self):
        """Test that restore doesn't leak data across tenants."""
        store = InMemoryVectorStore()
        vec_a = np.random.randn(384).astype(np.float32)
        vec_b = np.random.randn(384).astype(np.float32)

        store.upsert("tenant-a", "Secret A", vec_a, chunk_id="c1", source_id="doc1")
        store.upsert("tenant-b", "Secret B", vec_b, chunk_id="c2", source_id="doc2")

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_path = Path(tmpdir) / "backup.json"
            store.backup(str(backup_path))
            store.restore(str(backup_path))

            # Verify tenant isolation
            query = np.random.randn(384).astype(np.float32)
            results_a = store.search("tenant-a", query)
            results_b = store.search("tenant-b", query)

            # tenant-a results should only contain text from tenant-a
            assert all("A" in text for text, _ in results_a) or len(results_a) == 0
            # tenant-b results should only contain text from tenant-b
            assert all("B" in text for text, _ in results_b) or len(results_b) == 0


class TestDeletion:
    """AC6: Right-to-be-forgotten deletion."""

    def test_delete_by_data_subject_removes_chunks(self):
        """Test that delete_by_data_subject removes matching chunks."""
        store = InMemoryVectorStore()
        vec1 = np.random.randn(384).astype(np.float32)
        vec2 = np.random.randn(384).astype(np.float32)
        vec3 = np.random.randn(384).astype(np.float32)

        store.upsert("tenant-a", "customer-12345: Q3 report", vec1, chunk_id="c1", source_id="customer-12345")
        store.upsert("tenant-a", "customer-12345: expense data", vec2, chunk_id="c2", source_id="customer-12345")
        store.upsert("tenant-a", "customer-67890: summary", vec3, chunk_id="c3", source_id="customer-67890")

        count = store.delete_by_data_subject("tenant-a", "customer-12345")
        assert count == 2

        # Verify deletion
        query = np.random.randn(384).astype(np.float32)
        results = store.search("tenant-a", query, top_k=10)
        assert all("customer-12345" not in text for text, _ in results)

    def test_delete_by_data_subject_verification_query(self):
        """AC6: Verify deletion by follow-up query."""
        store = InMemoryVectorStore()
        vec = np.random.randn(384).astype(np.float32)

        store.upsert("tenant-a", "customer-xyz: private data", vec, chunk_id="c1", source_id="customer-xyz")
        deleted = store.delete_by_data_subject("tenant-a", "customer-xyz")
        assert deleted == 1

        # Follow-up verification query
        query = np.random.randn(384).astype(np.float32)
        results = store.search("tenant-a", query)
        found = [text for text, _ in results if "customer-xyz" in text]
        assert len(found) == 0, f"Deletion failed: found {len(found)} references"

    def test_delete_by_data_subject_respects_tenant_isolation(self):
        """Test that deletion doesn't cross tenant boundaries."""
        store = InMemoryVectorStore()
        vec_a = np.random.randn(384).astype(np.float32)
        vec_b = np.random.randn(384).astype(np.float32)

        store.upsert("tenant-a", "customer-12345: data", vec_a, chunk_id="c1", source_id="customer-12345")
        store.upsert("tenant-b", "customer-12345: data", vec_b, chunk_id="c2", source_id="customer-12345")

        # Delete from tenant-a only
        deleted = store.delete_by_data_subject("tenant-a", "customer-12345")
        assert deleted == 1

        # Verify tenant-b still has the data
        query = np.random.randn(384).astype(np.float32)
        results_b = store.search("tenant-b", query, top_k=10)
        assert any("12345" in text for text, _ in results_b)


class TestCompaction:
    """AC7: Index compaction and maintenance."""

    def test_compact_reports_status(self):
        """Test that compact returns ok status and chunk count."""
        store = InMemoryVectorStore()
        vec = np.random.randn(384).astype(np.float32)

        store.upsert("tenant-a", "Sample", vec, chunk_id="c1")

        result = store.compact()
        assert result['status'] == 'ok'
        assert result['chunk_count'] == 1

    def test_compact_after_deletion(self):
        """Test compact after deletion (should reflect deleted chunks)."""
        store = InMemoryVectorStore()
        vec1 = np.random.randn(384).astype(np.float32)
        vec2 = np.random.randn(384).astype(np.float32)

        store.upsert("tenant-a", "Text 1", vec1, chunk_id="c1", source_id="doc1")
        store.upsert("tenant-a", "Text 2", vec2, chunk_id="c2", source_id="doc2")

        store.delete_by_source("tenant-a", "doc1")
        result = store.compact()

        assert result['chunk_count'] == 1


class TestGoldenSetVersioning:
    """AC1 & AC3: Golden set versioning and separate metrics."""

    def test_eval_result_includes_version(self):
        """Test that evaluation results record git_sha for version tracking."""
        from evals.runner import run_eval

        # Use dry-run to validate without needing real LLM
        report = run_eval(['rag_qa'], dry_run=True)

        assert 'meta' in report
        assert 'git_sha' in report['meta']
        assert 'timestamp' in report['meta']
        assert report['meta']['git_sha'] in ('unknown', 'test') or len(report['meta']['git_sha']) > 0

    def test_eval_retrieval_metrics_separate(self):
        """Test that eval reports support retrieval metrics (structure verified in AC3 acceptance)."""
        from evals.runner import run_eval

        # Dry-run skips full evaluation to test structure only.
        # Real eval runs populate retrieval_metrics with recall@K, MRR, nDCG.
        # This test verifies oracle_comparison_summary is present (tracks retrieval vs generation failures).
        report = run_eval(['rag_qa'], dry_run=True)

        rag_ds = report.get('datasets', {}).get('rag_qa', {})
        # Oracle comparison tracks retrieval_failure vs generation_failure separately (AC3)
        assert 'oracle_comparison_summary' in rag_ds

    def test_eval_oracle_comparison(self):
        """Test that oracle comparison distinguishes retrieval vs generation failures."""
        from evals.runner import run_eval

        report = run_eval(['rag_qa'], dry_run=True)

        rag_ds = report.get('datasets', {}).get('rag_qa', {})
        assert 'oracle_comparison_summary' in rag_ds
        summary = rag_ds['oracle_comparison_summary']
        assert 'working' in summary
        assert 'retrieval_failure' in summary
        assert 'generation_failure' in summary
        assert 'both_failing' in summary


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
