import runpy


def test_proof_runs():
    runpy.run_path("proof-check/proof.py")
