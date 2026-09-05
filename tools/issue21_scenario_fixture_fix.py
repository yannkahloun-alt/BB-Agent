from pathlib import Path

path = Path("tests/test_evaluator.py")
text = path.read_text(encoding="utf-8")

old = '''def _inferred_exact(value: int, basis: str) -> KnownValue:
    return KnownValue(
        Representation.EXACT,
        KnowledgeClass.INFERRED,
        value=value,
        basis=(basis,),
    )
'''
new = '''def _inferred_point_distribution(value: int, basis: str) -> KnownValue:
    return KnownValue(
        Representation.DISTRIBUTION,
        KnowledgeClass.INFERRED,
        distribution=((value, 1.0),),
        basis=(basis,),
    )
'''
if text.count(old) != 1:
    raise RuntimeError("inferred helper seam not found exactly once")
text = text.replace(old, new)
text = text.replace("_inferred_exact(", "_inferred_point_distribution(")
path.write_text(text, encoding="utf-8")
print("issue #21 scenario fixture vocabulary corrected")
