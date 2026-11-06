"""Score the fields of a matched gold/model item pair.

Every applicable field gets one result (null handling as in the methodology):

  gold          model         result
  null          null          match
  value         same value    match
  value         null          missing   (the model left out a value gold has)
  null          value         extra     (the model filled a value gold leaves null)
  value         other value   wrong

The applicable fields are those of the gold item's kind (normalization.applicable_fields). A pair
is an exact match only when every applicable field matches, kind included.
"""

from dataclasses import dataclass

from flu_extractor.normalization import MISSING, applicable_fields, normalize_item

MATCH, MISSING_VALUE, EXTRA_VALUE, WRONG = "match", "missing", "extra", "wrong"


@dataclass(frozen=True)
class FieldResult:
    name: str
    gold: object     # normalized values
    model: object
    result: str      # MATCH, MISSING_VALUE, EXTRA_VALUE or WRONG

    @property
    def correct(self) -> bool:
        return self.result == MATCH


def compare_field(name: str, gold, model) -> FieldResult:
    if gold == model:
        return FieldResult(name, gold, model, MATCH)
    if model is None or model is MISSING:
        return FieldResult(name, gold, model, MISSING_VALUE)
    if gold is None or gold is MISSING:
        return FieldResult(name, gold, model, EXTRA_VALUE)
    return FieldResult(name, gold, model, WRONG)


@dataclass
class PairScore:
    """The field results of one matched pair."""

    fields: list[FieldResult]

    @property
    def correct_fields(self) -> int:
        return sum(f.correct for f in self.fields)

    @property
    def applicable(self) -> int:
        return len(self.fields)

    @property
    def accuracy(self) -> float:
        return self.correct_fields / self.applicable

    @property
    def exact(self) -> bool:
        return self.correct_fields == self.applicable

    @property
    def wrong_fields(self) -> list[str]:
        return [f.name for f in self.fields if not f.correct]


def score_pair(gold_item: dict, model_item: dict) -> PairScore:
    gold, model = normalize_item(gold_item), normalize_item(model_item)
    return PairScore([compare_field(name, gold[name], model[name]) for name in applicable_fields(gold["kind"])])
