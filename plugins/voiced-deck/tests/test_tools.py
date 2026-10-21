import base64
import copy
import json
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

PLUGIN = pathlib.Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
sys.path.insert(0, str(PLUGIN / "tools"))

from vdeck import asr, deckfile, deliver, manifest, perf as P, pngpack, script  # noqa: E402

DEMO = PLUGIN / "examples" / "demo"


class PngPack(unittest.TestCase):
    def test_round_trip_sizes(self):
        for n in (0, 1, 2, 3, 4, 5, 6143, 6144, 6145, 200_001):
            data = os.urandom(n)
            self.assertEqual(pngpack.unpack(pngpack.pack(data)), data, n)

    def test_header_is_big_endian_length(self):
        rgb = pngpack.pixels(pngpack.pack(b"hello"))
        self.assertEqual(struct.unpack(">I", rgb[:4])[0], 5)
        self.assertEqual(rgb[4:9], b"hello")

    def test_filtered_rgba_png_decodes(self):
        w, h = 3, 2
        px = bytes(range(w * h * 4))
        rows = b""
        for y in range(h):
            line = px[y * w * 4:(y + 1) * w * 4]
            sub = bytes((line[x] - (line[x - 4] if x >= 4 else 0)) & 0xFF for x in range(len(line)))
            rows += b"\x01" + sub
        chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
        png = pngpack.SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
        want = b"".join(px[i:i + 3] for i in range(0, len(px), 4))
        self.assertEqual(pngpack.pixels(png), want)

    def test_demo_audio_png_holds_the_m4a(self):
        self.assertEqual(pngpack.unpack((DEMO / "audio" / "deck.png").read_bytes()), (DEMO / "audio" / "deck.m4a").read_bytes())


class Delivery(unittest.TestCase):
    def test_pack_deck_loader(self):
        with tempfile.TemporaryDirectory() as d:
            deck = pathlib.Path(d) / "deck.html"
            (pathlib.Path(d) / "audio").mkdir()
            (pathlib.Path(d) / "audio" / "deck.png").write_bytes(pngpack.pack(b"x" * 64))
            deck.write_text((DEMO / "deck.html").read_text(encoding="utf-8"), encoding="utf-8")
            page, png, audio = deliver.pack_deck(deck)
            self.assertEqual(pngpack.unpack(png.read_bytes()).decode("utf-8"), deck.read_text(encoding="utf-8"))
            src = page.read_text(encoding="utf-8")
            parts = json.loads(src.split("var P=", 1)[1].split(".join", 1)[0])
            self.assertEqual("".join(parts), "audio/deck.png")
            self.assertNotIn('"audio/deck.png"].', src)
            self.assertIn('AUDIO="audio/deck.png"', src.replace(" ", ""))
            self.assertEqual(audio, "audio/deck.png")


    def test_demo_inline_png_is_the_current_deck(self):
        self.assertEqual(pngpack.unpack((DEMO / "deck.inline.png").read_bytes()), (DEMO / "deck.html").read_bytes(),
                         "run: voiced-deck pack-deck examples/demo/deck.html")


class Single(unittest.TestCase):
    CLI = PLUGIN / "tools" / "voiced-deck"

    def demo_copy(self, d, audio=True):
        deck = pathlib.Path(d) / "deck.html"
        deck.write_text((DEMO / "deck.html").read_text(encoding="utf-8"), encoding="utf-8")
        if audio:
            (pathlib.Path(d) / "audio").mkdir()
            (pathlib.Path(d) / "audio" / "deck.m4a").write_bytes((DEMO / "audio" / "deck.m4a").read_bytes())
        return deck

    def embedded(self, html):
        src = deckfile.manifest(html)["audio"]
        self.assertEqual(list(src), ["m4a"])
        self.assertTrue(src["m4a"].startswith("data:audio/mp4;base64,"))
        return base64.b64decode(src["m4a"].split(",", 1)[1])

    def test_no_external_audio_reference(self):
        with tempfile.TemporaryDirectory() as d:
            dest, n = deliver.pack_single(self.demo_copy(d))
            html = dest.read_text(encoding="utf-8")
            self.assertEqual(dest.name, "deck.single.html")
            ref = re.search(r"[\"'(][^\"'()\s]*\.(m4a|mp3|wav|png)[\"')?#]", html)
            self.assertIsNone(ref, ref and ref.group(0))
            self.assertEqual(self.embedded(html), (DEMO / "audio" / "deck.m4a").read_bytes())
            self.assertEqual(n, (DEMO / "audio" / "deck.m4a").stat().st_size)
            src = (DEMO / "deck.html").read_text(encoding="utf-8")
            self.assertEqual(deckfile.MANIFEST_RE.sub("", html), deckfile.MANIFEST_RE.sub("", src))

    def test_falls_back_to_the_packed_png_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            deck = self.demo_copy(d, audio=False)
            (pathlib.Path(d) / "audio").mkdir()
            (pathlib.Path(d) / "audio" / "deck.png").write_bytes((DEMO / "audio" / "deck.png").read_bytes())
            once, _ = deliver.pack_single(deck)
            twice, _ = deliver.pack_single(once, out=pathlib.Path(d) / "again.html")
            self.assertEqual(once.read_text(encoding="utf-8"), twice.read_text(encoding="utf-8"))

    def test_refuses_non_mp4_without_bitrate(self):
        with tempfile.TemporaryDirectory() as d:
            wav = pathlib.Path(d) / "voice.wav"
            wav.write_bytes(b"RIFF\0\0\0\0WAVEfmt " + b"\0" * 32)
            with self.assertRaises(SystemExit):
                deliver.pack_single(self.demo_copy(d), audio=wav)

    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_bitrate_shrinks_and_reports_size(self):
        with tempfile.TemporaryDirectory() as d:
            deck = self.demo_copy(d)
            loud = pathlib.Path(d) / "loud.m4a"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=20", "-ac", "2",
                            "-c:a", "aac", "-b:a", "192k", str(loud)], check=True)
            out = pathlib.Path(d) / "small.html"
            r = subprocess.run([sys.executable, "-I", str(self.CLI), "pack-single", "--deck", str(deck), "--audio", str(loud),
                                "--out", str(out), "--bitrate", "24k", "--max-mb", "0.01"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            lines = r.stdout.strip().splitlines()
            self.assertRegex(lines[0], r"small\.html: \d+\.\d\d MB in one file \(audio \d+ KB at 24k, no external audio\)")
            self.assertIn("warning: small.html is over 0.01 MB", lines[1])
            audio = self.embedded(out.read_text(encoding="utf-8"))
            self.assertEqual(audio[4:8], b"ftyp")
            self.assertLess(len(audio), loud.stat().st_size / 4)
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=channels", "-of", "csv=p=0", "-"],
                                   input=audio, capture_output=True)
            self.assertEqual(probe.stdout.strip(), b"1")

    def test_pack_deck_still_packs_a_single_file(self):
        with tempfile.TemporaryDirectory() as d:
            single, _ = deliver.pack_single(self.demo_copy(d))
            page, png, audio = deliver.pack_deck(single)
            self.assertEqual(audio, "")
            self.assertEqual(pngpack.unpack(png.read_bytes()), single.read_bytes())

    def test_demo_single_is_current(self):
        with tempfile.TemporaryDirectory() as d:
            fresh, _ = deliver.pack_single(DEMO / "deck.html", out=pathlib.Path(d) / "deck.single.html")
            self.assertEqual((DEMO / "deck.single.html").read_bytes(), fresh.read_bytes(),
                             "run: voiced-deck pack-single --deck examples/demo/deck.html")
            self.assertLess(fresh.stat().st_size, 1.5 * 2**20)


class Manifest(unittest.TestCase):
    def setUp(self):
        self.html = (DEMO / "deck.html").read_text(encoding="utf-8")
        self.man = deckfile.manifest(self.html)

    def test_demo_manifest_matches_script(self):
        self.assertIsNotNone(self.man)
        self.assertEqual(manifest.check(self.man, deckfile.pitch(self.html)), [])
        self.assertEqual(self.man["audio"], {"m4a": "audio/deck.m4a", "png": "audio/deck.png"})

    def test_embed_is_idempotent_and_clearable(self):
        once = deckfile.set_manifest(self.html, self.man)
        self.assertEqual(deckfile.set_manifest(once, self.man), once)
        self.assertEqual(once, self.html)
        cleared = deckfile.set_manifest(once, None)
        self.assertIsNone(deckfile.manifest(cleared))
        self.assertEqual(deckfile.set_manifest(cleared, self.man), self.html)

    def test_mismatch_is_reported(self):
        bad = copy.deepcopy(self.man)
        bad["slides"][1]["segments"].pop()
        self.assertTrue(any("slide 2" in e for e in manifest.check(bad, deckfile.pitch(self.html))))
        late = copy.deepcopy(self.man)
        late["slides"][2]["segments"][0]["start"] = 0.0
        self.assertTrue(any("before the previous" in e for e in manifest.check(late, deckfile.pitch(self.html))))

    def test_script_close_tag_is_escaped(self):
        m = copy.deepcopy(self.man)
        m["slides"][0]["segments"][0]["lines"][0]["text"] = "a </script> b"
        html = deckfile.set_manifest(self.html, m)
        self.assertIn("<\\/script>", html)
        self.assertEqual(deckfile.manifest(html)["slides"][0]["segments"][0]["lines"][0]["text"], "a </script> b")


class ScriptAndEngine(unittest.TestCase):
    def test_script_md_equals_deck_pitch(self):
        pitch = script.parse((DEMO / "script.md").read_text(encoding="utf-8"))
        self.assertEqual(pitch, deckfile.pitch((DEMO / "deck.html").read_text(encoding="utf-8")))
        self.assertEqual([len(p["segments"]) - 1 for p in pitch], [1, 2, 3, 3, 2, 2, 1])

    def test_demo_engine_equals_template(self):
        demo = (DEMO / "deck.html").read_text(encoding="utf-8")
        self.assertEqual(deckfile.sync_engine(demo, deckfile.TEMPLATE.read_text(encoding="utf-8")), demo)

    def test_static_builds_respect_layout(self):
        html = '<section class="slide" id="s1"><div data-only="wide"><i data-b="2"></i></div><i data-b="1"></i></section>'
        self.assertEqual(deckfile.static_builds(html)[0]["wide"], 2)
        self.assertEqual(deckfile.static_builds(html)[0]["narrow"], 1)

    def test_demo_is_small(self):
        self.assertLess((DEMO / "deck.html").stat().st_size, 200 * 1024)


class Performance(unittest.TestCase):
    def setUp(self):
        self.perf = P.load(DEMO / "performance.json")
        self.pitch = deckfile.pitch((DEMO / "deck.html").read_text(encoding="utf-8"))

    def test_demo_passes(self):
        err, _, stats = P.check(self.perf, self.pitch)
        self.assertEqual(err, [])
        self.assertEqual(stats["lines"], 34)

    def lint(self, **change):
        p = copy.deepcopy(self.perf)
        p["slides"][0]["segments"][0]["lines"][0].update(change)
        return P.check(p, self.pitch)

    def test_rules(self):
        self.assertTrue(any("direction marks" in e for e in self.lint(text="Hello [smiling] there.")[0]))
        self.assertTrue(any("unsupported tags" in e for e in self.lint(text="Hello <whisper> there.")[0]))
        self.assertTrue(any("long dash" in e for e in self.lint(text="Hello \u2014 there.")[0]))
        self.assertTrue(any("no direction" in e for e in self.lint(style="")[0]))
        self.assertTrue(any("gapAfterMs" in e for e in self.lint(gapAfterMs=5000)[0]))
        self.assertTrue(any("disfluencies" in e for e in self.lint(text="Uh, um, I mean, uh, so, so yes.")[0]))
        self.assertTrue(any("digits" in w for w in self.lint(text="We have 38 hives.")[1]))

    def test_segment_mismatch(self):
        p = copy.deepcopy(self.perf)
        p["slides"][2]["segments"].pop()
        self.assertTrue(any("slide 3" in e for e in P.check(p, self.pitch)[0]))

    def test_direction_is_deterministic_and_adds_notes(self):
        line = next(l for _, _, l in P.flat(self.perf) if "Varroa" in l["text"])
        d = P.direction(line, self.perf)
        self.assertEqual(d, P.direction(copy.deepcopy(line), copy.deepcopy(self.perf)))
        self.assertTrue(d.startswith(line["style"]))
        self.assertIn(self.perf["pronounce"]["Varroa"], d)
        self.assertLessEqual(max(len(P.direction(l, self.perf)) for _, _, l in P.flat(self.perf)), P.MAX_DIRECTION)


class Asr(unittest.TestCase):
    def test_numbers_normalise(self):
        self.assertEqual(asr.wer("Today it's one thousand two hundred and forty.", "Today, it's 1,240.")[0], 0.0)
        self.assertEqual(asr.wer("In twenty twenty-seven.", "In 2027.")[0], 0.0)
        self.assertEqual(asr.wer("We're raising one point two million dollars.", "We're raising $1.2 million.")[0], 0.0)
        self.assertEqual(asr.wer("Nine dollars a hive, a month.", "$9 a hive a month.")[0], 0.0)
        w, extra = asr.wer("Nine dollars a hive, a month.", "$9 a month.")
        self.assertTrue(asr.flagged({"wer": w, "extra": extra}), (w, extra))


class Scrub(unittest.TestCase):
    def test_scrub_check_catches_planted_secrets(self):
        planted = [x.replace("~", "") for x in ("/Us~ers/someone/notes", "pk~_live_abc123xyz", "pr~j_AbCdEf123", "owner~@corp.io", "R~$ 49,90", "Project Blue~bird weekly")]
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as cfg:
            subprocess.run(["git", "init", "-q", d], check=True)
            (pathlib.Path(d) / "leak.md").write_text("\n".join(planted), encoding="utf-8")
            private = pathlib.Path(cfg) / "private.txt"
            private.write_text("# test denylist\nproject blue" + "bird\n", encoding="utf-8")
            env = {**os.environ, "SCRUB_PRIVATE_FILE": str(private)}
            r = subprocess.run([sys.executable, "-I", str(REPO / "scripts" / "scrub_check.py"), d], capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertEqual(r.stdout.count("FAIL"), len(planted), r.stdout)

    def test_scrub_check_reads_embedded_audio_metadata(self):
        meta = b"\0\0\0\x18ftypM4A " + ("owner" + "@corp.io").encode()
        uri = "data:audio/mp4;base64," + base64.b64encode(meta).decode() + "/C" + "PF+"
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            (pathlib.Path(d) / "deck.single.html").write_text(f'<script>{{"m4a":"{uri}"}}</script>', encoding="utf-8")
            r = subprocess.run([sys.executable, "-I", str(REPO / "scripts" / "scrub_check.py"), d], capture_output=True, text=True)
            self.assertEqual(r.stdout.count("FAIL"), 1, r.stdout)
            self.assertIn("[embedded audio metadata]", r.stdout)

    def test_repo_is_clean(self):
        r = subprocess.run([sys.executable, "-I", str(REPO / "scripts" / "scrub_check.py")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
