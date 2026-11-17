from engine import detect, redact

text = ("Ravi Kumar, a 34-year-old cardiologist at KMC Hospital in Mangaluru, "
        "called on 12 March from 98450 12345. Email: ravi@kmc.com. "
        "My cousin lives behind the old bus stand.")

for t in (0.3, 0.5, 0.8):                 # this is your "dial"
    ents = detect(text, threshold=t)
    print(f"\nthreshold {t}")
    print(" mask:", redact(text, ents, "mask"))
    print(" fake:", redact(text, ents, "fake"))
