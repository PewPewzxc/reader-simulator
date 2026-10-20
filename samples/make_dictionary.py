"""English sample dictionary for the simulated SD card: WordNet 3.0 definitions of every word in the sample books.
  python -I make_dictionary.py <wordnet.zip> [book.epub ...]     (default: sd-card/books/*.epub)
wordnet.zip: nltk_data's corpora/wordnet.zip (WordNet 3.0, Princeton's licence: free to copy with its notice).
Writes sd-card/dictionaries/wordnet/wordnet.{ifo,idx,dict} (StarDict 2.4.2, plain text entries), its LICENSE,
and sd-card/.crosspoint/dictionary.bin, which makes it the reader's dictionary (CrossInk-family firmwares).
Inflected forms in the books ("walked") get their own index entry pointing at the base word's definition."""
import glob
import os
import re
import struct
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CARD = os.path.join(HERE, "sd-card")
NAME = "wordnet"
POS = {"noun": "n.", "verb": "v.", "adj": "adj.", "adv": "adv."}
# WordNet's own "morphy" rules: inflected ending -> base ending
SUFFIXES = {"noun": [("s", ""), ("ses", "s"), ("xes", "x"), ("zes", "z"), ("ches", "ch"), ("shes", "sh"),
                     ("men", "man"), ("ies", "y")],
            "verb": [("s", ""), ("ies", "y"), ("es", "e"), ("es", ""), ("ed", "e"), ("ed", ""), ("ing", "e"), ("ing", "")],
            "adj": [("er", ""), ("est", ""), ("er", "e"), ("est", "e")], "adv": []}


def wordnet(path):
    """{pos: {lemma: [gloss, ...]}} and {pos: {inflected: base}} from the zip."""
    z = zipfile.ZipFile(path)
    names = {os.path.basename(n): n for n in z.namelist()}
    senses, exceptions = {}, {}
    for pos in POS:
        glosses = {}
        for line in z.read(names["data." + pos]).decode("utf-8").splitlines():
            if line.startswith("  "):  # licence header
                continue
            head, _, gloss = line.partition(" | ")
            glosses[head.split(" ", 1)[0]] = gloss.strip()
        senses[pos] = {}
        for line in z.read(names["index." + pos]).decode("utf-8").splitlines():
            if line.startswith("  "):
                continue
            f = line.split()
            lemma, count = f[0], int(f[2])
            senses[pos][lemma] = [glosses[o] for o in f[-count:] if o in glosses]
        exceptions[pos] = {}
        for line in z.read(names[{"adj": "adj.exc", "adv": "adv.exc"}.get(pos, pos + ".exc")]).decode("utf-8").splitlines():
            f = line.split()
            if len(f) >= 2:
                exceptions[pos].setdefault(f[0], f[1])
    licence = z.read(names["LICENSE"]).decode("utf-8") if "LICENSE" in names else ""
    return senses, exceptions, licence


def book_words(paths):
    words = set()
    for p in paths:
        with zipfile.ZipFile(p) as z:
            for n in z.namelist():
                if n.endswith((".xhtml", ".html")):
                    text = re.sub(r"<[^>]+>", " ", z.read(n).decode("utf-8", "replace"))
                    words.update(w.lower().strip("'’") for w in re.findall(r"[A-Za-z][A-Za-z'’]*", text))
    return {w for w in words if w}


def base_forms(word, senses, exceptions):
    """WordNet lemmas a word in a book can stand for (morphy)."""
    found = []
    for pos in POS:
        candidates = [word, exceptions[pos].get(word)] + [word[:-len(a)] + b for a, b in SUFFIXES[pos] if word.endswith(a)]
        for c in candidates:
            if c and c in senses[pos] and c not in found:
                found.append(c)
    return found


def entry(lemma, senses):
    lines = []
    for pos, label in POS.items():
        for i, gloss in enumerate(senses[pos].get(lemma, []), 1):
            lines.append(f"{label} {i}. {gloss}")
    return "\n".join(lines)  # the reader shows the headword itself


def stardict_key(word):  # StarDict's order: g_ascii_strcasecmp, then strcmp
    b = word.encode("utf-8")
    return (b.lower(), b)


def main(zip_path, books):
    senses, exceptions, licence = wordnet(zip_path)
    lemmas, extra = set(), {}
    for w in book_words(books):
        bases = base_forms(w, senses, exceptions)
        lemmas.update(bases)
        if bases and w not in bases:
            extra[w] = bases[0]  # "walked" -> "walk"
    out = os.path.join(CARD, "dictionaries", NAME)  # where CrossInk-family firmwares list dictionaries
    os.makedirs(out, exist_ok=True)
    offsets, data = {}, bytearray()
    for lemma in sorted(lemmas):
        text = entry(lemma, senses).encode("utf-8")
        offsets[lemma] = (len(data), len(text))
        data += text
    index = [(lemma.replace("_", " "), offsets[lemma]) for lemma in lemmas]
    index += [(w, offsets[b]) for w, b in extra.items() if w.replace("_", " ") not in {i[0] for i in index}]
    index.sort(key=lambda e: stardict_key(e[0]))
    idx = b"".join(w.encode("utf-8") + b"\0" + struct.pack(">II", *o) for w, o in index)
    open(os.path.join(out, NAME + ".dict"), "wb").write(data)
    open(os.path.join(out, NAME + ".idx"), "wb").write(idx)
    open(os.path.join(out, NAME + ".ifo"), "w", encoding="utf-8", newline="\n").write(
        "StarDict's dict ifo file\nversion=2.4.2\n"
        f"bookname=WordNet 3.0 (sample: the words of the sample books)\nwordcount={len(index)}\n"
        f"idxfilesize={len(idx)}\nsametypesequence=m\nauthor=Princeton University\n"
        "description=WordNet 3.0 Copyright 2006 by Princeton University. All rights reserved. See LICENSE.txt.\n")
    open(os.path.join(out, "LICENSE.txt"), "w", encoding="utf-8", newline="\n").write(licence)
    os.makedirs(os.path.join(CARD, ".crosspoint"), exist_ok=True)
    open(os.path.join(CARD, ".crosspoint", "dictionary.bin"), "w", encoding="utf-8", newline="").write(
        f"/dictionaries/{NAME}/{NAME}")
    print(f"{len(index)} words ({len(lemmas)} with their own definition), {len(data) // 1024} KB, in {out}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:] or sorted(glob.glob(os.path.join(CARD, "books", "*.epub"))))
