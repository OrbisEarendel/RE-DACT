from gliner import GLiNER

model = GLiNER.from_pretrained("urchade/gliner_multi_pii-v1")

labels = ["person", "address", "organization", "phone number",
          "email", "date of birth", "job title", "medical condition"]

texts = [
    "Ravi Kumar, a 34-year-old cardiologist at KMC Hospital in Mangaluru, "
    "called on 12 March from 98450 12345 about his father's diagnosis.",

    "Please send the parcel to Priya Shetty, 2nd floor, Sri Residency, "
    "near Kadri Temple, Kadri Hills, Mangaluru 575002.",

    "My cousin works at Infosys in Mysuru and lives behind the old bus stand.",
]

for t in texts:
    print("\n", t)
    for e in model.predict_entities(t, labels, threshold=0.4):
        print(f"  {e['label']:18} {e['text']!r}  ({e['score']:.2f})")
