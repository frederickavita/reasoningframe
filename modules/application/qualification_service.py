class QualificationService(object):
    def decide_status(self, rule_signals, llm_fit_confidence):
        positive_count = len([s for s in rule_signals if s.get("polarity") == "positive"])
        negative_count = len([s for s in rule_signals if s.get("polarity") == "negative"])

        if negative_count > 0 and positive_count == 0:
            return "not_qualified"

        if llm_fit_confidence == "high" or positive_count > negative_count:
            return "qualified"

        return "uncertain"