import unittest

from flu_keywords import accept_token, flu_hits, is_flu_related, normalize


class TokenRules(unittest.TestCase):
    def test_flu_words_accepted(self):
        for w in ["flu", "flus", "influenza", "influenzas", "swineflu", "birdflu", "manflu", "wuflu", "dogflu",
                  "flulike", "theraflu", "tamiflu", "tamaflu", "xofluza", "oseltamivir", "zanamivir", "baloxavir",
                  "flumist", "flublok", "flugen", "influvac", "fluenz", "efluelda", "flushot", "flurona",
                  "fluey", "flunet", "fluview", "flusurvey", "influeza", "lnfluenza", "vaxigrip",
                  "infogripe", "agrippal", "grippe", "relenza", "favipiravir"]:
            self.assertTrue(accept_token(w), w)

    def test_lookalikes_denied(self):
        for w in ["influence", "influenced", "influential", "influencer", "influx", "fluid", "fluids", "fluctuate",
                  "fluctuations", "flurry", "flush", "flushed", "fluor", "fluoride", "fluorescent", "fluff",
                  "fluent", "flux", "reflux", "efflux", "affluent", "affluenza", "confluence", "superfluous",
                  "mellifluous", "flue", "flues", "flued", "unflued", "flute", "flutter", "fluke", "flung",
                  "fludarabine", "fluconazole", "fluticasone", "fluoxetine", "flummox", "flummery", "isoflurane",
                  "parainfluenza", "influenzae", "grip", "gripped", "gripping", "grips", "gripe", "poligrip",
                  "agriprocessors", "molnupiravir", "fluqe", "beeinflussen", "perfluorooctanoic", "flujo",
                  "flugelhorn", "fluilds", "fluridation", "microfludic", "fluiteq", "fluktuasi", "fluker"]:
            self.assertFalse(accept_token(w), w)


class TextRules(unittest.TestCase):
    def test_strain_and_name_without_flu_word(self):
        self.assertTrue(is_flu_related("Officials confirmed an H5N1 outbreak at the farm."))
        self.assertTrue(is_flu_related("HPAI was found in two flocks."))

    def test_ili_uppercase_only(self):
        self.assertTrue(is_flu_related("ILI activity rose again this week."))
        self.assertFalse(is_flu_related("The ili river flows north."))

    def test_place_and_person_names_not_flu(self):
        self.assertFalse(is_flu_related("Yamagata Prefecture in Japan"))
        self.assertFalse(is_flu_related("A Spanish lady at the ball"))
        self.assertTrue(is_flu_related("the Yamagata lineage"))
        self.assertTrue(is_flu_related("B/Victoria strain"))

    def test_english_only_scope(self):
        for w in ["vogelgrippe", "schweinegrippe", "gripa", "influensa"]:
            self.assertFalse(accept_token(w), w)
        for txt in ["la gripe aviar", "Vogelgrippe im Park", "今年流感很严重", "грипп в России"]:
            self.assertFalse(is_flu_related(txt), txt)

    def test_chemo_regimen_not_flu(self):
        self.assertFalse(is_flu_related("Patients received flu/cy lymphodepletion before infusion."))

    def test_ligature_and_broken_text(self):
        self.assertTrue(is_flu_related("review meeting on In?uenza A (H1N1)"))
        self.assertTrue(is_flu_related("recommending influ-enza vaccination"))
        self.assertTrue(is_flu_related("symptoms of the ﬂu"))

    def test_plain_non_flu(self):
        self.assertFalse(is_flu_related("Fluid prices fluctuate and the influence of markets grows."))
        self.assertFalse(is_flu_related("Haemophilus influenzae type b vaccine and sari fabrics."))

    def test_hits_report_source(self):
        hits = flu_hits("The flu and H5N1 and HPAI.")
        self.assertIn(("word", "seen", "flu"), hits)
        self.assertTrue(any(h[0] == "strain" for h in hits))
        self.assertTrue(any(h[1] == "ext" for h in hits))

    def test_normalize_keeps_other_text(self):
        self.assertEqual(normalize("hello world"), "hello world")


if __name__ == "__main__":
    unittest.main()
