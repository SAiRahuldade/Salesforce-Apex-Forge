- [x] Fix StateManager to handle directory paths by using a deterministic filename.
- [x] Fix SQLiteMemoryStore concurrency/persistence so concurrent writes don't lose records (stress test expects >=100).
- [x] Run targeted pytest: tests/integration/test_platform_integration.py::test_memory_stress_and_persistence
- [x] Run full file: tests/integration/test_platform_integration.py to confirm PermissionError setup failures are gone.
- [x] (Optional) Address remaining StarletteDeprecationWarning by switching to httpx2.
- [x] Fix API endpoint test to include endpoints in root response
- [x] Fix deployment test fixtures to use sandbox connections for sandbox tests

