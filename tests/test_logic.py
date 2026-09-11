"""Проверки логики XBIT888 без сети: python -m unittest discover tests"""
import importlib.util
import os
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "xbit888-boundless.pyw")

# хранилища пишут в %APPDATA% — в тестах уводим их во временную папку
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="xbit888-test-")

spec = importlib.util.spec_from_file_location("xbit", APP)
xb = importlib.util.module_from_spec(spec)
sys.modules["xbit"] = xb
spec.loader.exec_module(xb)


def wallet(i):
    return f"0x{i:040x}"


def rows(pcts, grouped=0):
    return [{"wallet": wallet(i), "amount": 1.0, "pct": p,
             "funder": "0xmaster" if i < grouped else None,
             "group": 1 if i < grouped else None, "checked": True}
            for i, p in enumerate(pcts)]


class HookTests(unittest.TestCase):
    def test_no_hook(self):
        info = xb.describe_v4_hook("0x" + "0" * 40, 3000)
        self.assertFalse(info["has_hook"])
        self.assertAlmostEqual(info["fee_pct"], 0.3)

    def test_real_launchpad_hook_takes_cut_but_cannot_block(self):
        # хук с 235 пулов Robinhood: afterSwap + afterSwapReturnsDelta, без beforeSwap
        info = xb.describe_v4_hook("0x4e3468951d49f2eea976ed0d6e75ffcb44a9a544", 0)
        self.assertTrue(info["can_take_cut"])
        self.assertFalse(info["can_block_swaps"])

    def test_before_swap_bit_means_can_block(self):
        address = "0x" + "0" * 36 + f"{1 << 7:04x}"
        self.assertTrue(xb.describe_v4_hook(address, 0)["can_block_swaps"])

    def test_dynamic_fee_flag(self):
        info = xb.describe_v4_hook("0x" + "0" * 40, 0x800000)
        self.assertTrue(info["dynamic_fee"])
        self.assertIsNone(info["fee_pct"])


class SignalTests(unittest.TestCase):
    def test_signals(self):
        buys = [{"wallet": wallet(i), "block": 100 if i < 3 else 105, "quote": 1000 + i, "nonce": 0}
                for i in range(5)]
        buys.append({"wallet": wallet(9), "block": 110, "quote": 50_000, "nonce": 40})
        sig = xb.compute_launch_signals(buys, launch_block=100)
        self.assertEqual(sig["total"], 6)
        self.assertEqual(sig["same_block"], 3)
        self.assertEqual(sig["fresh"], 5)
        self.assertEqual(sig["similar_spend"], 5)

    def test_similar_spend_needs_three(self):
        buys = [{"wallet": wallet(i), "block": 1, "quote": q, "nonce": 9} for i, q in enumerate((10, 11, 500))]
        self.assertEqual(xb.compute_launch_signals(buys, 0)["similar_spend"], 0)


class PayloadTests(unittest.TestCase):
    def test_grouping_by_shared_funder(self):
        per_wallet = {wallet(0): 50.0, wallet(1): 30.0, wallet(2): 20.0}
        funders = {wallet(0): "0xm", wallet(1): "0xm", wallet(2): None}
        data = xb._build_bundle_payload(per_wallet, 1000.0, 60, False, False, funders, False, None)
        self.assertEqual(list(data["bundle_clusters"]), ["0xm"])
        self.assertAlmostEqual(data["bundle_pct"], 8.0)
        self.assertEqual([r["group"] for r in data["wallet_rows"]], [1, 1, None])


class RiskTests(unittest.TestCase):
    def test_clean_launch(self):
        data = {"early_pct": 6.0, "bundle_pct": 0.0, "bundle_clusters": {}, "wallet_rows": rows([1.2, 0.9])}
        risk = xb.assess_token_risk(data)
        self.assertEqual((risk["score"], risk["level"]), (100, "low"))

    def test_heavy_bundle_is_dirty(self):
        data = {"early_pct": 97.4, "bundle_pct": 97.4, "bundle_clusters": {"0xm": {}},
                "wallet_rows": rows([11.5, 11.4, 11.0], grouped=3)}
        risk = xb.assess_token_risk(data)
        self.assertEqual(risk["level"], "high")
        self.assertLess(risk["score"], 50)

    def test_bundle_never_labelled_clean(self):
        # бандл уже вышел и баллов почти не сняли — всё равно не "чистый запуск"
        data = {"early_pct": 10.0, "bundle_pct": 5.0, "bundle_clusters": {"0xm": {}},
                "wallet_rows": rows([3.0, 2.0], grouped=2)}
        self.assertNotEqual(xb.assess_token_risk(data)["level"], "low")

    def test_unverified_links_never_clean(self):
        data = {"early_pct": 5.0, "bundle_pct": 0.0, "bundle_clusters": {}, "wallet_rows": rows([1.0]),
                "links_total": 4, "links_failed": 3}
        risk = xb.assess_token_risk(data)
        self.assertEqual(risk["level"], "caution")
        self.assertIn("risk_unverified", [key for _p, key, _kw in risk["reasons"]])

    def test_dev_linked_through_hop_wallet(self):
        data = {"early_pct": 10.0, "bundle_pct": 5.0, "bundle_clusters": {"0xmaster": {}},
                "wallet_rows": rows([3.0, 2.0], grouped=2), "dev": {"address": "0xDEV", "held_pct": 0.0},
                "masters": {wallet(0): {"hop1": "0xdev", "hop2": None}}}
        self.assertTrue(xb.dev_linked_to_bundle(data))

    def test_holders_replace_early_concentration(self):
        data = {"early_pct": 10.0, "bundle_pct": 0.0, "bundle_clusters": {}, "wallet_rows": rows([5.0] * 10),
                "holders": {"top_pct": 80.0, "n": 10}}
        keys = [k for _p, k, _kw in xb.assess_token_risk(data, {wallet(i): 5.0 for i in range(10)})["reasons"]]
        self.assertIn("risk_top_holders", keys)
        self.assertNotIn("risk_concentration", keys)


class PriceTests(unittest.TestCase):
    def test_native_stable_price(self):
        # ETH = $2500 при USDG с 6 знаками: raw = 2500 * 1e6 / 1e18
        raw = 2500 * 10 ** 6 / 10 ** 18
        sqrt_price = int((raw ** 0.5) * 2 ** 96)
        self.assertAlmostEqual(xb.v4_price_in_quote(sqrt_price, True, 18, 6), 2500, delta=0.01)

    def test_token_as_currency1(self):
        raw = 1_000_000 / 1        # 1 натив = 1 000 000 токенов (оба с 18 знаками)
        sqrt_price = int((raw ** 0.5) * 2 ** 96)
        self.assertAlmostEqual(xb.v4_price_in_quote(sqrt_price, False, 18, 18), 1e-6, delta=1e-12)


class StoreTests(unittest.TestCase):
    def test_bundler_memory_flags_repeat_master(self):
        memory = xb.BundlerMemory()
        memory.record("0xTokenA", "AAA", {"0xMaster": {"wallets": [1, 2], "pct": 40.0}})
        found = xb.BundlerMemory().lookup({"0xmaster"}, exclude_token="0xTokenB")
        self.assertIn("0xmaster", found)
        self.assertEqual(xb.BundlerMemory().lookup({"0xmaster"}, exclude_token="0xtokena"), {})

    def test_history_dedupes_and_exports(self):
        history = xb.CheckHistory()
        history.add({"token": "0xAbc", "score": 10})
        history.add({"token": "0xabc", "score": 90})
        self.assertEqual(len(history.data), 1)
        self.assertEqual(history.data[0]["score"], 90)
        path = os.path.join(os.environ["APPDATA"], "h.csv")
        history.export_csv(path)
        with open(path, encoding="utf-8-sig") as fh:
            self.assertIn("score", fh.readline())


class ImageTests(unittest.TestCase):
    def test_png_encoder(self):
        image = xb.stack_bgra([{"rows": [bytes((0, 0, 255, 255)) * 2], "w": 2, "h": 1}], 3, (8, 9, 10))
        path = os.path.join(os.environ["APPDATA"], "t.png")
        xb.bgra_to_png(image, path)
        with open(path, "rb") as fh:
            blob = fh.read()
        self.assertTrue(blob.startswith(b"\x89PNG\r\n\x1a\n"))
        idat = blob[blob.index(b"IDAT") + 4:blob.index(b"IEND") - 8]
        raw = zlib.decompress(idat)
        self.assertEqual(raw, b"\x00" + bytes((255, 0, 0)) * 2 + bytes((8, 9, 10)))


if __name__ == "__main__":
    unittest.main()
