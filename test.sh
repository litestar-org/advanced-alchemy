#!/usr/bin/env bash
# Usage:
#   ./test.sh [--output_path results.xml] base   — regression tests (must pass without solution)
#   ./test.sh [--output_path results.xml] new    — new tests (must FAIL without solution, PASS with it)
#
# All tests use an in-memory SQLite database; no network access is required.

set -euo pipefail

OUTPUT_PATH=""
if [ "${1:-}" = "--output_path" ]; then
  OUTPUT_PATH="$2"
  shift 2
fi

MODE="${1:-new}"

PYTEST="uv run pytest"

JUNIT_ARGS=()
if [ -n "$OUTPUT_PATH" ]; then
  JUNIT_ARGS=("--junitxml=$OUTPUT_PATH")
fi

case "$MODE" in
  base)
    echo "=== Running baseline regression tests ==="
    # All test_model_from_dict_* tests and related helpers in test_repository.py
    # import from tests.fixtures.uuid.models, which registers the 'memory://'
    # fsspec backend at import time. That backend is not available in this
    # environment, so these tests fail on the pinned baseline commit too.
    # Deselecting the whole affected block keeps the rest of the suite clean.
    exec $PYTEST tests/unit/ \
      --ignore=tests/unit/test_polymorphic.py \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_includes_relationship_attributes \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_backward_compatibility \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_ignores_unknown_attributes \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_empty_relationship \
      --deselect=tests/unit/test_repository.py::test_update_many_data_conversion_handles_mixed_types \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_nested_single_dict \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_nested_list_of_dicts \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_deeply_nested \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_none_relationship \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_empty_list_relationship \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_mixed_list \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_preserves_existing_instance \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_single_item_for_collection \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_performance_baseline \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_performance_nested \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_many_to_many_relationship \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_tuple_for_collection \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_with_model_key \
      --deselect=tests/unit/test_repository.py::test_model_from_dict_with_mapped_model_field \
      --deselect=tests/unit/test_repository.py::test_convert_relationship_value_helper \
      -q --tb=short "${JUNIT_ARGS[@]}"
    ;;
  new)
    echo "=== Running new polymorphic-support tests ==="
    exec $PYTEST tests/unit/test_polymorphic.py \
      -v --tb=short "${JUNIT_ARGS[@]}"
    ;;
  *)
    echo "Unknown mode '$MODE'. Use: base | new" >&2
    exit 1
    ;;
esac
