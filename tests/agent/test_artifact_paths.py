from __future__ import annotations

from salesforce_ai_engineer.agent.artifact_paths import (
    ensure_meta_files,
    iter_artifact_files,
    resolve_salesforce_path,
)


def test_resolve_salesforce_path_for_apex_and_trigger() -> None:
    assert resolve_salesforce_path("FormValidation.cls") == (
        "force-app/main/default/classes/FormValidation.cls"
    )
    assert resolve_salesforce_path("ContactFormValidationTrigger.trigger") == (
        "force-app/main/default/triggers/ContactFormValidationTrigger.trigger"
    )


def test_iter_artifact_files_supports_filename_map_and_structured_payload() -> None:
    artifacts = {
        "FormValidation.cls": "public class FormValidation {}",
        "artifact-1": {"type": "apex", "name": "Helper", "code": "public class Helper {}"},
    }

    files = dict(iter_artifact_files(artifacts))

    assert "FormValidation.cls" in files
    assert files["Helper.cls"] == "public class Helper {}"


def test_ensure_meta_files_adds_missing_meta_xml() -> None:
    files = ensure_meta_files([("FormValidation.cls", "public class FormValidation {}")])

    names = {name for name, _ in files}
    assert "FormValidation.cls-meta.xml" in names
