"""PII masking with Microsoft Presidio, run BEFORE any text goes to an LLM.

The CFPB already masks most details (you will see XXXX), but a real deployment would use unmasked internal text,
so we build the habit: names, phones, e-mails, SSNs, card and account numbers are replaced by tags like <PERSON>.
We use the small spaCy model (en_core_web_sm) so it runs on a laptop.
We deliberately do NOT mask locations (state/city give useful context) or the company name.
"""
from collections import Counter
from functools import lru_cache

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

ENTITIES = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "US_SSN", "CREDIT_CARD", "US_BANK_NUMBER",
            "IBAN_CODE", "IP_ADDRESS", "ACCOUNT_NUMBER"]


@lru_cache(maxsize=1)
def _engines():
    nlp = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]}).create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])
    # long digit runs (8-17 digits) are usually account numbers; the amounts {$123.45} are not matched
    analyzer.registry.add_recognizer(PatternRecognizer(
        supported_entity="ACCOUNT_NUMBER", patterns=[Pattern("long_digits", r"(?<![\d.$,])\d{8,17}(?![\d.,]*\d)", 0.6)]))
    return analyzer, AnonymizerEngine()


def mask_pii(text):
    """Return (masked_text, Counter of what was found)."""
    analyzer, anonymizer = _engines()
    found = analyzer.analyze(text=text, language="en", entities=ENTITIES, score_threshold=0.4)
    operators = {e: OperatorConfig("replace", {"new_value": f"<{e}>"}) for e in ENTITIES}
    masked = anonymizer.anonymize(text=text, analyzer_results=found, operators=operators).text
    return masked, Counter(r.entity_type for r in found)
