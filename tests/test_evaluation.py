import json
from pathlib import Path

import pytest

from email_classifier_app.evaluation import evaluate, main, read_partitions, validate_review_log


DATASET = Path(__file__).resolve().parents[1] / "data" / "avaliacao_piloto.csv"


def test_evaluation_uses_same_test_ids_in_every_scenario():
    report = evaluate(DATASET.read_bytes())
    ids = report["partitions"]["teste"]["ids"]
    assert len(ids) == 15
    assert len(report["test"]) == 6
    for result in report["test"].values():
        assert [row["id"] for row in result["predictions"]] == ids
        assert sum(map(sum, result["confusion_matrix"])) == len(ids)
    before = report["test"]["hibrido_antes"]["predictions"]
    after = report["test"]["hibrido_depois"]["predictions"]
    assert [row for row in before if row["source"] == "rule"] == [
        row for row in after if row["source"] == "rule"
    ]


def test_rejects_groups_crossing_partitions():
    data = DATASET.read_bytes().replace(b"E01,cartao-suspeito,teste,", b"E01,credencial-vazada,teste,")
    with pytest.raises(ValueError, match="mais de uma particao"):
        read_partitions(data)


def test_rejects_duplicate_text_even_when_group_and_id_are_different():
    data = DATASET.read_bytes()
    data += b"\nX42,grupo-novo,teste,a@exemplo.invalid,Servidor fora do ar,Incidente de seguran\xc3\xa7a. O servi\xc3\xa7o est\xc3\xa1 indispon\xc3\xadvel e precisa de interven\xc3\xa7\xc3\xa3o.,Urgente\n"
    with pytest.raises(ValueError, match="Texto duplicado"):
        read_partitions(data)


def test_review_log_requires_matching_confirmations_and_does_not_return_reviewer_data():
    examples = read_partitions(DATASET.read_bytes())["revisao"]
    header = "id,reviewer,category_before,category_confirmed,justification\n"
    lines = [
        f"{row.id},REVISOR,{'Pessoal' if row.category != 'Pessoal' else 'Trabalho'},{row.category},motivo"
        for row in examples
    ]
    evidence = validate_review_log((header + "\n".join(lines)).encode(), examples)
    assert evidence["changed"] == evidence["confirmed"] == len(examples)
    assert set(evidence) == {"changed", "confirmed", "sha256"}
    with pytest.raises(ValueError, match="sem registro"):
        validate_review_log((header + "\n".join(lines[1:])).encode(), examples)
    with pytest.raises(ValueError, match="fora do lote"):
        validate_review_log((header + "\n".join(lines + [lines[0]])).encode(), examples)


def test_cli_rejects_changed_fingerprint(tmp_path, monkeypatch, capsys):
    signature = tmp_path / "signature.json"
    review = tmp_path / "review.csv"
    output = tmp_path / "result.json"
    monkeypatch.setattr("sys.argv", ["evaluation", "--freeze", "--output", str(signature)])
    main()
    metadata = json.loads(signature.read_text(encoding="utf-8"))
    metadata["sklearn"] = "changed"
    signature.write_text(json.dumps(metadata), encoding="utf-8")
    monkeypatch.setattr("sys.argv", [
        "evaluation", str(DATASET), "--lock", str(signature), "--review-log", str(review), "--output", str(output)
    ])
    with pytest.raises(SystemExit) as exit_result:
        main()
    assert exit_result.value.code == 1
    assert "difere da assinatura congelada" in capsys.readouterr().err
    assert not output.exists()
