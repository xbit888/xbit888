#!/usr/bin/env python3
"""
CA Watcher — live-трекер покупок/продаж токена по CA.
Тёмный интерфейс в стиле трейдинг-терминалов, с переключением языка (RU/EN/中文).

Двойной клик по файлу (если .pyw ассоциирован с pythonw.exe) открывает окно
без консоли. Если не открывается двойным кликом, запустите из терминала:
    python ca_watcher_gui.pyw

Источники данных — публичные и бесплатные, без ключей и кошельков:
  - frontend-api-v3.pump.fun — статус bonding curve
  - публичный RPC сети (Solana / Ethereum / BSC / Base / Arbitrum / Robinhood / ...)
  - api.dexscreener.com — метаданные токена/пары после миграции на DEX
"""

import concurrent.futures
import json
import queue
import re
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import ttk, font as tkfont
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Локализация
# ---------------------------------------------------------------------------

LANGS = ["ru", "en", "zh"]
LANG_NAMES = {"ru": "RU", "en": "EN", "zh": "中文"}

TR = {
    "app_title": {"ru": "XBIT888", "en": "XBIT888", "zh": "XBIT888"},
    "app_subtitle": {"ru": "live-трекер сделок по адресу токена", "en": "live token-trade watcher", "zh": "代币实时交易监控"},
    "ca_label": {"ru": "Адрес токена (CA)", "en": "Token address (CA)", "zh": "代币地址 (CA)"},
    "ca_placeholder": {"ru": "Вставьте CA и нажмите Пуск", "en": "Paste CA and press Start", "zh": "粘贴代币地址并点击开始"},
    "interval_label": {"ru": "Интервал, с", "en": "Interval, s", "zh": "刷新间隔(秒)"},
    "rpc_label": {"ru": "Свой RPC (необязательно — снимает лимиты)",
                   "en": "Custom RPC (optional — lifts rate limits)",
                   "zh": "自定义 RPC（可选，可解除频率限制）"},
    "stats_hint": {"ru": "за текущую сессию наблюдения",
                    "en": "for the current watch session",
                    "zh": "本次监控会话统计"},
    "stat_buys_hint": {"ru": "сделок на покупку", "en": "buy trades", "zh": "买入笔数"},
    "stat_sells_hint": {"ru": "сделок на продажу", "en": "sell trades", "zh": "卖出笔数"},
    "stat_net_hint": {"ru": "покупки минус продажи", "en": "buy volume minus sell volume", "zh": "买入量减卖出量"},
    "start": {"ru": "▶ ПУСК", "en": "▶ START", "zh": "▶ 开始"},
    "stop": {"ru": "■ СТОП", "en": "■ STOP", "zh": "■ 停止"},
    "clear": {"ru": "Очистить", "en": "Clear", "zh": "清除"},
    "lang_label": {"ru": "Язык", "en": "Language", "zh": "语言"},

    "status_ready": {"ru": "Готов", "en": "Ready", "zh": "就绪"},
    "status_running": {"ru": "Работает", "en": "Running", "zh": "运行中"},
    "status_stopped": {"ru": "Остановлено", "en": "Stopped", "zh": "已停止"},
    "status_enter_ca": {"ru": "Введите CA токена", "en": "Enter a token CA", "zh": "请输入代币地址"},

    "col_time": {"ru": "Время", "en": "Time", "zh": "时间"},
    "col_type": {"ru": "Тип", "en": "Type", "zh": "类型"},
    "col_wallet": {"ru": "Кошелёк", "en": "Wallet", "zh": "钱包"},
    "col_amount": {"ru": "Токены", "en": "Tokens", "zh": "代币数量"},
    "col_value": {"ru": "Сумма", "en": "Value", "zh": "价值"},
    "col_tx": {"ru": "Транзакция", "en": "Tx", "zh": "交易"},
    "hint_click": {"ru": "Двойной клик: кошелёк — скопировать, транзакция — открыть в браузере",
                   "en": "Double-click: wallet — copy, tx — open in browser",
                   "zh": "双击：钱包—复制地址，交易—在浏览器中打开"},
    "copied": {"ru": "Скопировано: {value}", "en": "Copied: {value}", "zh": "已复制：{value}"},

    "trade_buy": {"ru": "ПОКУПКА", "en": "BUY", "zh": "买入"},
    "trade_sell": {"ru": "ПРОДАЖА", "en": "SELL", "zh": "卖出"},

    "meta_name": {"ru": "Токен", "en": "Token", "zh": "代币"},
    "meta_network": {"ru": "Сеть", "en": "Network", "zh": "网络"},
    "meta_dex": {"ru": "DEX", "en": "DEX", "zh": "交易所"},
    "meta_price": {"ru": "Цена", "en": "Price", "zh": "价格"},
    "meta_liquidity": {"ru": "Ликвидность", "en": "Liquidity", "zh": "流动性"},
    "meta_source_pumpfun": {"ru": "pump.fun (bonding curve)", "en": "pump.fun (bonding curve)", "zh": "pump.fun（联合曲线）"},
    "meta_placeholder": {"ru": "—", "en": "—", "zh": "—"},

    "log_invalid_ca": {"ru": "Не похоже на адрес токена (Solana mint или EVM 0x...).",
                        "en": "Doesn't look like a token address (Solana mint or EVM 0x...).",
                        "zh": "地址格式不正确（应为 Solana mint 或 EVM 0x... 地址）。"},
    "log_checking_pumpfun": {"ru": "Проверяю pump.fun для {ca}...",
                              "en": "Checking pump.fun for {ca}...",
                              "zh": "正在通过 pump.fun 查询 {ca} ..."},
    "log_checking_dexscreener": {"ru": "Ищу информацию о токене через Dexscreener...",
                                  "en": "Looking up the token on Dexscreener...",
                                  "zh": "正在通过 Dexscreener 查询代币信息..."},
    "log_dexscreener_error": {"ru": "Не удалось обратиться к Dexscreener: {e}",
                               "en": "Could not reach Dexscreener: {e}",
                               "zh": "无法连接 Dexscreener: {e}"},
    "log_no_pair": {"ru": "Нет торговой пары для этого адреса (токен новый / нет ликвидности).",
                     "en": "No trading pair found for this address (new token / no liquidity).",
                     "zh": "未找到该地址的交易对（代币过新或无流动性）。"},
    "log_v4_detected": {"ru": "Обнаружен Uniswap V4 (сеть: {chain}). Ищу PoolManager...",
                         "en": "Uniswap V4 detected (network: {chain}). Locating PoolManager...",
                         "zh": "检测到 Uniswap V4（网络：{chain}）。正在查找 PoolManager..."},
    "log_v4_poolmanager_not_found": {"ru": "Не удалось найти PoolManager (возможно, у токена ещё не было сделок).",
                                      "en": "Could not locate PoolManager (the token may not have traded yet).",
                                      "zh": "未能找到 PoolManager（该代币可能尚无交易）。"},
    "log_unknown_chain": {"ru": "Неизвестная сеть '{chain}'.",
                           "en": "Unknown network '{chain}'.",
                           "zh": "未知网络 '{chain}'。"},
    "log_watching_pumpfun": {"ru": "Слежу за bonding curve: {addr}",
                              "en": "Watching bonding curve: {addr}",
                              "zh": "正在监控联合曲线：{addr}"},
    "log_watching_solana": {"ru": "Слежу за пулом (Solana): {addr}",
                             "en": "Watching pool (Solana): {addr}",
                             "zh": "正在监控资金池（Solana）：{addr}"},
    "log_watching_evm": {"ru": "Слежу за парой (EVM): {addr}",
                          "en": "Watching pair (EVM): {addr}",
                          "zh": "正在监控交易对（EVM）：{addr}"},
    "log_watching_v4": {"ru": "Слежу за пулом Uniswap V4: {addr}",
                         "en": "Watching Uniswap V4 pool: {addr}",
                         "zh": "正在监控 Uniswap V4 资金池：{addr}"},
    "log_poolmanager_label": {"ru": "PoolManager: {addr}", "en": "PoolManager: {addr}", "zh": "PoolManager: {addr}"},
    "log_rpc_error": {"ru": "Ошибка RPC ({e}), повтор через {interval}с",
                       "en": "RPC error ({e}), retrying in {interval}s",
                       "zh": "RPC 错误（{e}），{interval} 秒后重试"},
    "log_block_number_error": {"ru": "Не удалось получить номер блока: {e}",
                                "en": "Could not fetch block number: {e}",
                                "zh": "无法获取区块高度：{e}"},
    "log_eth_getlogs_error": {"ru": "Ошибка eth_getLogs ({e}), повтор через {interval}с",
                               "en": "eth_getLogs error ({e}), retrying in {interval}s",
                               "zh": "eth_getLogs 错误（{e}），{interval} 秒后重试"},
    "log_pumpfun_migrated": {"ru": "Токен мигрировал на DEX — нажмите Стоп и Пуск заново.",
                              "en": "Token migrated to a DEX — press Stop then Start again.",
                              "zh": "代币已迁移到 DEX——请点击停止后重新开始。"},
    "log_unexpected_error": {"ru": "Неожиданная ошибка: {e}", "en": "Unexpected error: {e}", "zh": "发生意外错误：{e}"},

    "card_bundle_analysis": {"ru": "АНАЛИЗ БАНДЛОВ", "en": "BUNDLE ANALYSIS", "zh": "捆绑分析"},
    "card_trades": {"ru": "СДЕЛКИ", "en": "TRADES", "zh": "交易"},
    "col_funder": {"ru": "Кошелёк-раздатчик", "en": "Funder wallet", "zh": "资金来源钱包"},
    "col_wallets": {"ru": "Кошельков", "en": "Wallets", "zh": "钱包数"},
    "col_supply_pct": {"ru": "% предложения", "en": "% of supply", "zh": "占供应量"},
    "bundle_window_fmt": {"ru": "окно запуска: {w}с", "en": "launch window: {w}s", "zh": "上线窗口：{w} 秒"},
    "bundle_verdict_checking": {"ru": "идёт проверка...", "en": "checking...", "zh": "检测中..."},
    "bundle_verdict_bundled": {"ru": "ПОХОЖЕ НА БАНДЛ", "en": "LOOKS BUNDLED", "zh": "疑似捆绑"},
    "bundle_verdict_clean": {"ru": "признаков бандла не найдено", "en": "no bundle signs found", "zh": "未发现捆绑迹象"},
    "bundle_verdict_early_only": {"ru": "только % ранних покупок (раздатчик не проверялся)",
                                   "en": "early-buy % only (funder not checked)",
                                   "zh": "仅早期买入占比（未检测资金来源）"},
    "bundle_verdict_na": {"ru": "нет данных", "en": "no data", "zh": "无数据"},
    "bundle_early_fmt": {"ru": "Ранние покупки: {pct:.1f}% предложения · {wallets} кошельков",
                          "en": "Early buys: {pct:.1f}% of supply · {wallets} wallets",
                          "zh": "早期买入：占供应量 {pct:.1f}% · {wallets} 个钱包"},
    "row_bundle": {"ru": "БАНДЛ", "en": "BUNDLE", "zh": "捆绑检测"},
    "bundle_checking_short": {"ru": "проверка...", "en": "checking...", "zh": "检测中..."},
    "bundle_row_na": {"ru": "нет данных", "en": "n/a", "zh": "无数据"},
    "bundle_row_early_only": {"ru": "{pct:.0f}% рано (без проверки раздатчика)",
                               "en": "{pct:.0f}% early (no funder check)",
                               "zh": "早期买入 {pct:.0f}%（未检测资金来源）"},
    "bundle_row_bundled": {"ru": "⚠ {pct:.0f}% ПОХОЖЕ НА БАНДЛ", "en": "⚠ {pct:.0f}% LOOKS BUNDLED", "zh": "⚠ 疑似捆绑 {pct:.0f}%"},
    "bundle_row_clean": {"ru": "✓ признаков не найдено", "en": "✓ no signs found", "zh": "✓ 未发现迹象"},
    "check_bundles": {"ru": "🔍 Бандлы", "en": "🔍 Bundles", "zh": "🔍 捆绑检测"},
    "bundle_checking": {"ru": "Проверяю бандлы...", "en": "Checking bundles...", "zh": "正在检测捆绑买入..."},
    "bundle_scanning_launch": {"ru": "Ищу самые первые сделки после запуска токена...",
                                "en": "Scanning the earliest trades after launch...",
                                "zh": "正在扫描代币刚上线时的最早交易..."},
    "bundle_no_history": {"ru": "Не удалось найти историю сделок для этого адреса.",
                           "en": "Could not find trade history for this address.",
                           "zh": "未能找到该地址的交易历史。"},
    "bundle_no_early_buys": {"ru": "В окне запуска не найдено ни одной покупки.",
                              "en": "No buys found in the launch window.",
                              "zh": "在上线窗口内未发现任何买入。"},
    "bundle_no_pair": {"ru": "Не удалось найти торговую пару для проверки бандлов.",
                        "en": "Could not find a trading pair to check bundles.",
                        "zh": "未能找到可用于检测捆绑买入的交易对。"},
    "bundle_evm_unsupported": {"ru": "Проверка бандлов пока поддерживается только для Solana.",
                                "en": "Bundle check currently supports Solana only.",
                                "zh": "捆绑检测目前仅支持 Solana。"},
    "bundle_result_title": {"ru": "Результат проверки бандлов", "en": "Bundle check result", "zh": "捆绑检测结果"},
    "bundle_result_early": {"ru": "Скуплено в первые {window}с после запуска: {pct:.1f}% от предложения ({wallets} кошельков)",
                             "en": "Bought within {window}s of launch: {pct:.1f}% of supply ({wallets} wallets)",
                             "zh": "上线后 {window} 秒内买入：占供应量 {pct:.1f}%（{wallets} 个钱包）"},
    "bundle_result_bundled": {"ru": "Из них похоже на бандл (общий кошелёк-раздатчик): {pct:.1f}% от предложения",
                               "en": "Of that, looks bundled (shared funding wallet): {pct:.1f}% of supply",
                               "zh": "其中疑似捆绑买入（共用同一资金来源钱包）：占供应量 {pct:.1f}%"},
    "bundle_result_none": {"ru": "Признаков бандла (общего кошелька-раздатчика) не найдено — похоже на органические покупки.",
                            "en": "No bundle signs found (no shared funding wallet) — looks organic.",
                            "zh": "未发现捆绑迹象（没有共用资金来源钱包）——看起来是自然买入。"},
    "bundle_result_cluster": {"ru": "  • {n} кошельков от {funder} — {pct:.1f}% от предложения",
                               "en": "  • {n} wallets funded by {funder} — {pct:.1f}% of supply",
                               "zh": "  • {n} 个钱包由 {funder} 提供资金 — 占供应量 {pct:.1f}%"},
    "bundle_result_cap_note": {"ru": "(проверено только {n} крупнейших ранних кошельков)",
                                "en": "(only the {n} largest early wallets were checked)",
                                "zh": "（仅检查了最大的 {n} 个早期钱包）"},
    "bundle_funder_unsupported_note": {
        "ru": "Проверка общего кошелька-раздатчика для этой сети пока не поддерживается — показан только % ранних покупок.",
        "en": "Shared-funder check isn't supported for this network yet — showing early-buy % only.",
        "zh": "该网络暂不支持共用资金来源检测——仅显示早期买入占比。"},

    "live": {"ru": "LIVE", "en": "LIVE", "zh": "LIVE"},
    "offline": {"ru": "ОСТАНОВЛЕНО", "en": "OFFLINE", "zh": "已停止"},
    "waiting": {"ru": "ожидание токена...", "en": "waiting for a token...", "zh": "等待代币..."},
    "header_stat_buys": {"ru": "ПОКУПКИ", "en": "BUYS", "zh": "买入"},
    "header_stat_sells": {"ru": "ПРОДАЖИ", "en": "SELLS", "zh": "卖出"},
    "header_stat_clock": {"ru": "ВРЕМЯ", "en": "CLOCK", "zh": "时间"},

    "card_token_info": {"ru": "ТОКЕН", "en": "TOKEN INFO", "zh": "代币信息"},
    "card_live_feed": {"ru": "ЛЕНТА СДЕЛОК", "en": "LIVE FEED", "zh": "实时交易"},
    "card_live_stats": {"ru": "СТАТИСТИКА", "en": "LIVE STATS", "zh": "实时统计"},

    "row_network": {"ru": "СЕТЬ", "en": "NETWORK", "zh": "网络"},
    "row_dex": {"ru": "DEX", "en": "DEX", "zh": "交易所"},
    "row_price": {"ru": "ЦЕНА", "en": "PRICE", "zh": "价格"},
    "row_liquidity": {"ru": "ЛИКВИДНОСТЬ", "en": "LIQUIDITY", "zh": "流动性"},

    "last_price_label": {"ru": "MCAP", "en": "MCAP", "zh": "MCAP"},
    "no_chart_data": {"ru": "нет данных для графика", "en": "no chart data yet", "zh": "暂无图表数据"},

    "stat_buy_volume": {"ru": "Объём покупок", "en": "Buy volume", "zh": "买入量"},
    "stat_sell_volume": {"ru": "Объём продаж", "en": "Sell volume", "zh": "卖出量"},
    "stat_net_flow": {"ru": "ЧИСТЫЙ ПОТОК", "en": "NET FLOW", "zh": "净流入"},
}


class Translator:
    def __init__(self, lang="ru"):
        self.lang = lang

    def t(self, key, **kwargs):
        table = TR.get(key, {})
        template = table.get(self.lang) or table.get("en") or key
        try:
            return template.format(**kwargs)
        except Exception:
            return template


# ---------------------------------------------------------------------------
# Константы / общие HTTP-хелперы
# ---------------------------------------------------------------------------

DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/{}"

DEFAULT_EVM_RPCS = {
    "ethereum": "https://eth.llamarpc.com",
    "bsc": "https://bsc-dataseed.binance.org",
    "base": "https://mainnet.base.org",
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "polygon": "https://polygon-rpc.com",
    "avalanche": "https://api.avax.network/ext/bc/C/rpc",
    "optimism": "https://mainnet.optimism.io",
    "robinhood": "https://rpc.mainnet.chain.robinhood.com",
}

DEFAULT_SOLANA_RPC = "https://api.mainnet-beta.solana.com"

# окно "запуска" токена, в котором ищем скоординированные закупы (бандлы)
BUNDLE_WINDOW_SECONDS = 60

CHAIN_DISPLAY_NAMES = {
    "ethereum": "Ethereum", "bsc": "BSC", "base": "Base", "arbitrum": "Arbitrum",
    "polygon": "Polygon", "avalanche": "Avalanche", "optimism": "Optimism",
    "robinhood": "Robinhood", "solana": "Solana",
}


def chain_display_name(chain_id):
    chain_id = (chain_id or "").lower()
    return CHAIN_DISPLAY_NAMES.get(chain_id, chain_id.capitalize())


def dex_display_name(dex_id):
    return (dex_id or "").capitalize()
PUMPFUN_COIN_URL = "https://frontend-api-v3.pump.fun/coins/{}"
PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

EXPLORER_TX = {
    "solana": "https://solscan.io/tx/{}",
    "ethereum": "https://etherscan.io/tx/{}",
    "bsc": "https://bscscan.com/tx/{}",
    "base": "https://basescan.org/tx/{}",
    "arbitrum": "https://arbiscan.io/tx/{}",
    "polygon": "https://polygonscan.com/tx/{}",
    "avalanche": "https://snowtrace.io/tx/{}",
    "optimism": "https://optimistic.etherscan.io/tx/{}",
    "robinhood": "https://robinhoodchain.blockscout.com/tx/{}",
}
EXPLORER_ADDRESS = {
    "solana": "https://solscan.io/account/{}",
    "ethereum": "https://etherscan.io/address/{}",
    "bsc": "https://bscscan.com/address/{}",
    "base": "https://basescan.org/address/{}",
    "arbitrum": "https://arbiscan.io/address/{}",
    "polygon": "https://polygonscan.com/address/{}",
    "avalanche": "https://snowtrace.io/address/{}",
    "optimism": "https://optimistic.etherscan.io/address/{}",
    "robinhood": "https://robinhoodchain.blockscout.com/address/{}",
}


def explorer_tx_url(chain_id, tx_hash):
    template = EXPLORER_TX.get(chain_id)
    return template.format(tx_hash) if template else tx_hash


def explorer_address_url(chain_id, address):
    template = EXPLORER_ADDRESS.get(chain_id)
    return template.format(address) if template else address

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
UNISWAP_V4_SWAP_TOPIC = "0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f"

EVM_CA_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
SOLANA_CA_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def http_get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "ca-watcher/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post_json(url, payload, timeout=15):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", "User-Agent": "ca-watcher/1.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def detect_chain_by_format(ca):
    if EVM_CA_RE.match(ca):
        return "evm"
    if SOLANA_CA_RE.match(ca):
        return "solana"
    return None


def fetch_dexscreener_info(ca):
    data = http_get_json(DEXSCREENER_TOKEN_URL.format(ca))
    pairs = data.get("pairs") or []
    if not pairs:
        return None
    pairs.sort(key=lambda p: (p.get("liquidity") or {}).get("usd", 0) or 0, reverse=True)
    best = pairs[0]
    return {
        "chainId": best.get("chainId"),
        "dexId": best.get("dexId"),
        "pairAddress": best.get("pairAddress"),
        "baseToken": best.get("baseToken", {}),
        "quoteToken": best.get("quoteToken", {}),
        "priceUsd": best.get("priceUsd"),
        "priceNative": best.get("priceNative"),
        "liquidityUsd": (best.get("liquidity") or {}).get("usd"),
        "marketCapUsd": best.get("marketCap") or best.get("fdv"),
        "pairCreatedAt": best.get("pairCreatedAt"),
        "url": best.get("url"),
    }


# ---------------------------------------------------------------------------
# pump.fun bonding curve
# ---------------------------------------------------------------------------

def fetch_pumpfun_info(mint):
    try:
        return http_get_json(PUMPFUN_COIN_URL.format(mint), timeout=10)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def verify_pumpfun_curve(rpc_url, bonding_curve):
    try:
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
            "params": [bonding_curve, {"encoding": "base64"}],
        }
        resp = http_post_json(rpc_url, payload, timeout=10)
        value = (resp.get("result") or {}).get("value")
        return bool(value) and value.get("owner") == PUMP_PROGRAM_ID
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return False


def pumpfun_extract_trade(tx, curve_pda, assoc_curve, decimals=6):
    if not tx or not tx.get("meta") or tx["meta"].get("err"):
        return None
    msg = tx["transaction"]["message"]
    program_ids = [ix.get("programId") for ix in msg.get("instructions", [])]
    if PUMP_PROGRAM_ID not in program_ids:
        return None
    outer_idx = program_ids.index(PUMP_PROGRAM_ID)

    inner_ixs = []
    for grp in tx["meta"].get("innerInstructions") or []:
        if grp.get("index") == outer_idx:
            inner_ixs = grp.get("instructions") or []
            break
    if not inner_ixs:
        return None

    is_buy = None
    token_amount_raw = None
    for ix in inner_ixs:
        if ix.get("program") != "spl-token":
            continue
        parsed = ix.get("parsed") or {}
        if parsed.get("type") not in ("transfer", "transferChecked"):
            continue
        info = parsed.get("info", {})
        amount = info.get("amount")
        if amount is None and "tokenAmount" in info:
            amount = info["tokenAmount"].get("amount")
        if info.get("source") == assoc_curve:
            is_buy, token_amount_raw = True, amount
        elif info.get("destination") == assoc_curve:
            is_buy, token_amount_raw = False, amount

    if is_buy is None:
        return None

    sol_candidates = []
    for ix in inner_ixs:
        if ix.get("program") != "system":
            continue
        parsed = ix.get("parsed") or {}
        if parsed.get("type") != "transfer":
            continue
        info = parsed.get("info", {})
        if is_buy and info.get("destination") == curve_pda:
            sol_candidates.append(info)
        elif not is_buy and info.get("source") == curve_pda:
            sol_candidates.append(info)

    if not sol_candidates:
        return None
    best = max(sol_candidates, key=lambda i: i.get("lamports", 0))
    wallet = best.get("source") if is_buy else best.get("destination")

    return {
        "is_buy": is_buy,
        "wallet": wallet,
        "token_amount": int(token_amount_raw) / (10 ** decimals) if token_amount_raw else 0.0,
        "sol_amount": best.get("lamports", 0) / 1e9,
    }


def watch_pumpfun(mint, curve_pda, assoc_curve, rpc_url, interval, decimals, emit, stop_event, tr):
    emit("info", tr.t("log_watching_pumpfun", addr=curve_pda))
    seen = set()
    first_pass = True
    tick = 0

    while not stop_event.is_set():
        try:
            sigs = solana_get_signatures(rpc_url, curve_pda, limit=15)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            emit("error", tr.t("log_rpc_error", e=e, interval=interval))
            stop_event.wait(interval)
            continue

        for s in reversed(sigs):
            sig = s.get("signature")
            if sig in seen:
                continue
            seen.add(sig)
            if first_pass or s.get("err"):
                continue
            try:
                tx = solana_get_transaction(rpc_url, sig)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                continue

            trade = pumpfun_extract_trade(tx, curve_pda, assoc_curve, decimals)
            if not trade:
                continue
            ts = s.get("blockTime")
            ts_str = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "?"
            emit("trade", {
                "time": ts_str, "is_buy": trade["is_buy"], "wallet": trade["wallet"],
                "wallet_url": explorer_address_url("solana", trade["wallet"]),
                "amount": f"{trade['token_amount']:,.2f}", "amount_raw": trade["token_amount"],
                "quote_amount": f"{trade['sol_amount']:,.4f}", "quote_amount_raw": trade["sol_amount"],
                "quote_symbol": "SOL",
                "tx": sig, "tx_url": explorer_tx_url("solana", sig),
            })

        first_pass = False
        tick += 1
        if tick % 12 == 0:
            pf_info = fetch_pumpfun_info(mint)
            if pf_info and pf_info.get("complete"):
                emit("error", tr.t("log_pumpfun_migrated"))
                return

        stop_event.wait(interval)


# ---------------------------------------------------------------------------
# Solana (DEX-пулы после миграции)
# ---------------------------------------------------------------------------

def solana_get_signatures(rpc_url, address, limit=25, before=None):
    params = {"limit": limit}
    if before:
        params["before"] = before
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
        "params": [address, params],
    }
    return http_post_json(rpc_url, payload).get("result") or []


def solana_get_transaction(rpc_url, signature):
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
        "params": [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
    }
    return http_post_json(rpc_url, payload).get("result")


def solana_extract_buys(tx, mint, pool_owner_hint=None):
    if not tx or not tx.get("meta"):
        return []
    meta = tx["meta"]
    pre = {b["accountIndex"]: b for b in (meta.get("preTokenBalances") or []) if b.get("mint") == mint}
    post = {b["accountIndex"]: b for b in (meta.get("postTokenBalances") or []) if b.get("mint") == mint}

    buys = []
    for idx, post_bal in post.items():
        pre_bal = pre.get(idx)
        pre_amt = float(pre_bal["uiTokenAmount"]["uiAmountString"]) if pre_bal and pre_bal["uiTokenAmount"]["uiAmountString"] else 0.0
        post_amt = float(post_bal["uiTokenAmount"]["uiAmountString"]) if post_bal["uiTokenAmount"]["uiAmountString"] else 0.0
        delta = post_amt - pre_amt
        owner = post_bal.get("owner")
        if delta > 0 and owner and owner != pool_owner_hint:
            buys.append((owner, delta))
    return buys


def solana_get_token_supply(rpc_url, mint):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "getTokenSupply", "params": [mint]}
    result = http_post_json(rpc_url, payload).get("result")
    value = (result or {}).get("value") or {}
    return float(value.get("uiAmountString") or 0)


def _get_signatures_with_retry(rpc_url, address, limit, before=None, tries=3):
    """getSignaturesForAddress с ретраями. Без этого одиночный 429 от публичного RPC
    обрывал весь анализ бандлов необработанным исключением."""
    for attempt in range(tries):
        try:
            return solana_get_signatures(rpc_url, address, limit=limit, before=before)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt < tries - 1:
                time.sleep(0.6 * (attempt + 1))
    return []


def _fetch_transactions_parallel(rpc_url, signatures, stop_event, workers=6):
    """Тянет транзакции окна запуска в несколько потоков. Последовательно с паузами
    это занимало десятки секунд — а анализ бандлов должен быть быстрым."""
    results = []
    if not signatures:
        return results
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_get_transaction_with_retry, rpc_url, sig) for sig in signatures]
        for fut in concurrent.futures.as_completed(futures):
            if stop_event.is_set():
                break
            try:
                tx = fut.result()
            except Exception:
                tx = None
            if tx:
                results.append(tx)
    return results


def _get_transaction_with_retry(rpc_url, signature, tries=3):
    """getTransaction с ретраями — публичный RPC часто отдаёт 429 под нагрузкой."""
    for attempt in range(tries):
        try:
            return solana_get_transaction(rpc_url, signature)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt < tries - 1:
                time.sleep(0.5 * (attempt + 1))
    return None


def find_early_signatures(rpc_url, address, window_seconds, max_pages=15, page_size=100):
    """Пагинирует назад до самого начала истории адреса (или до потолка max_pages),
    затем возвращает подписи из первых window_seconds после самой первой сделки —
    то есть "окно запуска" токена."""
    all_sigs = []
    before = None
    for _ in range(max_pages):
        batch = _get_signatures_with_retry(rpc_url, address, page_size, before)
        if not batch:
            break
        all_sigs.extend(batch)
        before = batch[-1]["signature"]
        if len(batch) < page_size:
            break

    if not all_sigs:
        return [], None, False

    all_sigs.sort(key=lambda s: s.get("blockTime") or 0)
    launch_time = all_sigs[0].get("blockTime")
    hit_cap = len(all_sigs) >= max_pages * page_size
    early = [s for s in all_sigs if not s.get("err") and (s.get("blockTime") or 0) <= (launch_time or 0) + window_seconds]
    return early, launch_time, hit_cap


def find_wallet_funder(rpc_url, wallet, max_pages=5, page_size=100):
    """Находит самую первую транзакцию кошелька и адрес, который его профинансировал
    (system transfer, где destination == wallet). None, если не удалось определить."""
    before = None
    oldest_batch = None
    for _ in range(max_pages):
        batch = _get_signatures_with_retry(rpc_url, wallet, page_size, before)
        if not batch:
            break
        oldest_batch = batch
        before = batch[-1]["signature"]
        if len(batch) < page_size:
            break

    if not oldest_batch:
        return None
    oldest_sig = oldest_batch[-1]["signature"]
    tx = _get_transaction_with_retry(rpc_url, oldest_sig)
    if not tx or not tx.get("meta"):
        return None

    for ix in tx["transaction"]["message"].get("instructions", []):
        parsed = ix.get("parsed") or {}
        if ix.get("program") == "system" and parsed.get("type") == "transfer":
            info = parsed.get("info", {})
            if info.get("destination") == wallet:
                return info.get("source")
    return None


def check_pumpfun_bundles(mint, curve_pda, assoc_curve, decimals, total_supply, rpc_url,
                           window_seconds, emit, tr, stop_event, max_wallets=25):
    emit("info", tr.t("bundle_scanning_launch"))
    early_sigs, launch_time, hit_cap = find_early_signatures(rpc_url, curve_pda, window_seconds)
    if not early_sigs:
        emit("bundle_result", {"error": tr.t("bundle_no_history")})
        return

    per_wallet = {}
    for tx in _fetch_transactions_parallel(rpc_url, [s["signature"] for s in early_sigs], stop_event):
        trade = pumpfun_extract_trade(tx, curve_pda, assoc_curve, decimals)
        if trade and trade["is_buy"]:
            per_wallet[trade["wallet"]] = per_wallet.get(trade["wallet"], 0.0) + trade["token_amount"]

    _finish_bundle_check(per_wallet, total_supply, launch_time, hit_cap, window_seconds,
                          lambda w: find_wallet_funder(rpc_url, w), emit, tr, stop_event, max_wallets)


def check_solana_dex_bundles(mint, pair_address, decimals, total_supply, rpc_url,
                              window_seconds, emit, tr, stop_event, max_wallets=25):
    emit("info", tr.t("bundle_scanning_launch"))
    early_sigs, launch_time, hit_cap = find_early_signatures(rpc_url, pair_address, window_seconds)
    if not early_sigs:
        emit("bundle_result", {"error": tr.t("bundle_no_history")})
        return

    per_wallet = {}
    for tx in _fetch_transactions_parallel(rpc_url, [s["signature"] for s in early_sigs], stop_event):
        for owner, amount in solana_extract_buys(tx, mint, pool_owner_hint=pair_address):
            per_wallet[owner] = per_wallet.get(owner, 0.0) + amount

    _finish_bundle_check(per_wallet, total_supply, launch_time, hit_cap, window_seconds,
                          lambda w: find_wallet_funder(rpc_url, w), emit, tr, stop_event, max_wallets)


def _finish_bundle_check(per_wallet, total_supply, launch_time, hit_cap, window_seconds,
                          funder_fn, emit, tr, stop_event, max_wallets, funder_unsupported=False):
    if not per_wallet:
        emit("bundle_result", {"error": tr.t("bundle_no_early_buys")})
        return

    wallets_by_size = sorted(per_wallet.items(), key=lambda kv: kv[1], reverse=True)[:max_wallets]
    truncated = len(per_wallet) > max_wallets

    funders = {}
    if not funder_unsupported:
        # параллельно, но небольшим пулом: последовательный обход с паузами
        # растягивал проверку на десятки секунд
        wallets = [w for w, _a in wallets_by_size]
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            future_map = {pool.submit(funder_fn, w): w for w in wallets}
            for fut in concurrent.futures.as_completed(future_map):
                if stop_event.is_set():
                    return
                wallet = future_map[fut]
                try:
                    funders[wallet] = fut.result()
                except Exception:
                    funders[wallet] = None

    clusters = {}
    for wallet, funder in funders.items():
        if funder:
            clusters.setdefault(funder, []).append(wallet)
    raw_clusters = {f: ws for f, ws in clusters.items() if len(ws) >= 2}

    early_total = sum(per_wallet.values())
    early_pct = (early_total / total_supply * 100) if total_supply else 0.0

    bundle_clusters = {}
    bundle_total = 0.0
    for funder, wallets in raw_clusters.items():
        cluster_amount = sum(per_wallet[w] for w in wallets)
        bundle_total += cluster_amount
        bundle_clusters[funder] = {
            "wallets": wallets,
            "amount": cluster_amount,
            "pct": (cluster_amount / total_supply * 100) if total_supply else 0.0,
        }
    bundle_pct = (bundle_total / total_supply * 100) if total_supply else 0.0

    emit("bundle_result", {
        "early_pct": early_pct,
        "bundle_pct": bundle_pct,
        "early_wallets": len(per_wallet),
        "bundle_clusters": bundle_clusters,
        "window_seconds": window_seconds,
        "hit_cap": hit_cap,
        "truncated": truncated,
        "funder_unsupported": funder_unsupported,
    })


BLOCKSCOUT_API_BASE = {
    "robinhood": "https://robinhoodchain.blockscout.com",
}

BLOCKSCOUT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ca-watcher/1.0",
    "Accept": "application/json",
}


def evm_find_wallet_funder(chain_id, wallet, max_pages=4):
    """Ищет самую первую входящую нативную транзакцию кошелька через Blockscout API
    (для сетей, где такой обозреватель есть — например Robinhood). Без него у EVM
    нет дешёвого способа перечислить историю кошелька, поэтому для остальных сетей
    эта проверка просто не выполняется (см. funder_unsupported)."""
    base_url = BLOCKSCOUT_API_BASE.get(chain_id)
    if not base_url:
        return None

    from urllib.parse import urlencode
    next_params = None
    oldest = None
    for _ in range(max_pages):
        url = f"{base_url}/api/v2/addresses/{wallet}/transactions"
        if next_params:
            url += "?" + urlencode(next_params)
        try:
            req = urllib.request.Request(url, headers=BLOCKSCOUT_HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            break
        items = data.get("items") or []
        if items:
            oldest = items[-1]
        next_params = data.get("next_page_params")
        if not next_params:
            break

    if not oldest:
        return None
    try:
        value = int(oldest.get("value") or 0)
    except (TypeError, ValueError):
        value = 0
    to_addr = (oldest.get("to") or {}).get("hash") or ""
    from_addr = (oldest.get("from") or {}).get("hash")
    if value > 0 and to_addr.lower() == wallet.lower():
        return from_addr
    return None


def evm_estimate_block_by_timestamp(rpc_url, target_ts):
    """Прикидывает номер блока по unix-таймстампу через среднее время блока —
    у EVM нет прямого способа спросить RPC 'какой блок был в момент X'."""
    latest = int(evm_rpc_call(rpc_url, "eth_blockNumber", []), 16)
    latest_block = evm_rpc_call(rpc_url, "eth_getBlockByNumber", [hex(latest), False])
    latest_ts = int(latest_block["timestamp"], 16)

    ref_num = max(0, latest - 200000)
    ref_block = evm_rpc_call(rpc_url, "eth_getBlockByNumber", [hex(ref_num), False])
    ref_ts = int(ref_block["timestamp"], 16)

    span_blocks = latest - ref_num
    span_time = latest_ts - ref_ts
    block_time = (span_time / span_blocks) if span_blocks > 0 and span_time > 0 else 2.0

    estimated = int(latest - (latest_ts - target_ts) / block_time)
    return max(0, min(estimated, latest)), block_time, latest


def _scan_evm_logs(rpc_url, address, topics, start_block, window_seconds, block_time,
                    latest_block, max_chunk=3000, max_chunks=10, stop_event=None):
    end_block = min(latest_block, start_block + int(window_seconds / block_time * 2) + max_chunk)
    cur = max(0, start_block - 50)  # небольшой запас на неточность оценки блока
    logs = []
    chunks = 0
    while cur <= end_block and chunks < max_chunks:
        if stop_event is not None and stop_event.is_set():
            break
        to_block = min(cur + max_chunk, end_block)
        try:
            batch = evm_rpc_call(rpc_url, "eth_getLogs", [{
                "address": address, "topics": topics,
                "fromBlock": hex(cur), "toBlock": hex(to_block),
            }])
            logs.extend(batch or [])
        except Exception:
            pass
        cur = to_block + 1
        chunks += 1
        time.sleep(0.15)
    return logs


def check_evm_bundles(ca, chain_id, info, rpc_url, window_seconds, emit, tr, stop_event, max_wallets=25):
    emit("info", tr.t("bundle_scanning_launch"))

    pair_address = info["pairAddress"]
    created_at_ms = info.get("pairCreatedAt")
    if not created_at_ms:
        emit("bundle_result", {"error": tr.t("bundle_no_history")})
        return
    target_ts = created_at_ms / 1000

    try:
        decimals = evm_get_decimals(rpc_url, ca)
    except Exception:
        decimals = 18

    total_supply = 0
    try:
        price_usd = float(info["priceUsd"]) if info.get("priceUsd") else None
        mcap_usd = float(info["marketCapUsd"]) if info.get("marketCapUsd") else None
        if price_usd and mcap_usd:
            total_supply = mcap_usd / price_usd
    except (TypeError, ValueError, ZeroDivisionError):
        pass

    try:
        start_block, block_time, latest_block = evm_estimate_block_by_timestamp(rpc_url, target_ts)
    except Exception as e:
        emit("bundle_result", {"error": tr.t("log_block_number_error", e=e)})
        return

    per_wallet = {}

    if len(pair_address) == 66:
        pool_manager = find_uniswap_v4_pool_manager(rpc_url, ca)
        if not pool_manager:
            emit("bundle_result", {"error": tr.t("log_v4_poolmanager_not_found")})
            return
        quote_address = info["quoteToken"].get("address")
        is_token0 = int(ca, 16) < int(quote_address, 16)

        logs = _scan_evm_logs(rpc_url, pool_manager, [UNISWAP_V4_SWAP_TOPIC, pair_address],
                               start_block, window_seconds, block_time, latest_block, stop_event=stop_event)
        buys_by_tx = {}
        for lg in logs:
            amount0 = evm_word_signed(lg["data"], 0)
            amount1 = evm_word_signed(lg["data"], 1)
            our_amount = amount0 if is_token0 else amount1
            if our_amount > 0:  # положительное = трейдер получает наш токен = покупка
                buys_by_tx[lg["transactionHash"]] = our_amount / (10 ** decimals)

        for tx_hash, amount in buys_by_tx.items():
            if stop_event.is_set():
                return
            try:
                tx = evm_rpc_call(rpc_url, "eth_getTransactionByHash", [tx_hash])
                wallet = tx.get("from") if tx else None
            except Exception:
                wallet = None
            if wallet:
                per_wallet[wallet] = per_wallet.get(wallet, 0.0) + amount
            time.sleep(0.15)
    else:
        pair_topic = evm_pad_address_topic(pair_address)
        logs = _scan_evm_logs(rpc_url, ca, [TRANSFER_TOPIC], start_block, window_seconds,
                               block_time, latest_block, stop_event=stop_event)
        for lg in logs:
            topics = lg.get("topics") or []
            if len(topics) < 3 or topics[1].lower() != pair_topic.lower():
                continue  # интересуют только переводы ИЗ пула трейдеру, т.е. покупки
            wallet = evm_topic_to_address(topics[2])
            amount = int(lg.get("data", "0x0"), 16) / (10 ** decimals)
            per_wallet[wallet] = per_wallet.get(wallet, 0.0) + amount

    funder_unsupported = chain_id not in BLOCKSCOUT_API_BASE
    _finish_bundle_check(per_wallet, total_supply, int(target_ts), False, window_seconds,
                          lambda w: evm_find_wallet_funder(chain_id, w), emit, tr, stop_event,
                          max_wallets, funder_unsupported=funder_unsupported)


def run_bundle_check(ca, emit, tr, stop_event, window_seconds=BUNDLE_WINDOW_SECONDS, rpc_override=None):
    ca = ca.strip()
    fmt = detect_chain_by_format(ca)
    if fmt == "evm":
        emit("info", tr.t("bundle_checking"))
        info = fetch_dexscreener_info(ca)
        if not info or not info.get("pairAddress"):
            emit("bundle_result", {"error": tr.t("bundle_no_pair")})
            return
        chain_id = (info.get("chainId") or "").lower()
        rpc_url = rpc_override or DEFAULT_EVM_RPCS.get(chain_id, DEFAULT_EVM_RPCS["ethereum"])
        check_evm_bundles(ca, chain_id, info, rpc_url, window_seconds, emit, tr, stop_event)
        return
    if fmt != "solana":
        emit("bundle_result", {"error": tr.t("bundle_evm_unsupported")})
        return

    pf_info = fetch_pumpfun_info(ca)
    rpc_url = rpc_override or DEFAULT_SOLANA_RPC
    if pf_info and verify_pumpfun_curve(rpc_url, pf_info["bonding_curve"]):
        decimals = pf_info.get("base_decimals", 6)
        total_supply = (pf_info.get("total_supply") or 0) / (10 ** decimals)
        if not pf_info.get("complete"):
            check_pumpfun_bundles(ca, pf_info["bonding_curve"], pf_info["associated_bonding_curve"],
                                  decimals, total_supply, rpc_url, window_seconds, emit, tr, stop_event)
            return
        # мигрировал на DEX — тот же принцип, но по пулу
        info = fetch_dexscreener_info(ca)
        if info and info.get("pairAddress") and (info.get("chainId") or "").lower() == "solana":
            check_solana_dex_bundles(ca, info["pairAddress"], decimals, total_supply, rpc_url,
                                      window_seconds, emit, tr, stop_event)
            return

    info = fetch_dexscreener_info(ca)
    if not info or not info.get("pairAddress") or (info.get("chainId") or "").lower() != "solana":
        emit("bundle_result", {"error": tr.t("bundle_no_pair")})
        return
    try:
        total_supply = solana_get_token_supply(rpc_url, ca)
    except Exception:
        total_supply = 0
    check_solana_dex_bundles(ca, info["pairAddress"], 0, total_supply, rpc_url,
                              window_seconds, emit, tr, stop_event)


def watch_solana(ca, pair_address, rpc_url, interval, emit, stop_event, tr):
    emit("info", tr.t("log_watching_solana", addr=pair_address))
    seen = set()
    first_pass = True

    while not stop_event.is_set():
        try:
            sigs = solana_get_signatures(rpc_url, pair_address, limit=15)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            emit("error", tr.t("log_rpc_error", e=e, interval=interval))
            stop_event.wait(interval)
            continue

        for s in reversed(sigs):
            sig = s.get("signature")
            if sig in seen:
                continue
            seen.add(sig)
            if first_pass or s.get("err"):
                continue
            try:
                tx = solana_get_transaction(rpc_url, sig)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                continue

            buys = solana_extract_buys(tx, ca, pool_owner_hint=pair_address)
            ts = s.get("blockTime")
            ts_str = time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "?"
            for owner, amount in buys:
                emit("trade", {
                    "time": ts_str, "is_buy": True, "wallet": owner,
                    "wallet_url": explorer_address_url("solana", owner),
                    "amount": f"{amount:,.4f}", "amount_raw": amount,
                    "quote_amount": "", "quote_amount_raw": None, "quote_symbol": "",
                    "tx": sig, "tx_url": explorer_tx_url("solana", sig),
                })

        first_pass = False
        stop_event.wait(interval)


# ---------------------------------------------------------------------------
# EVM (Transfer-based, V2/V3-стиль пулов)
# ---------------------------------------------------------------------------

def evm_rpc_call(rpc_url, method, params):
    resp = http_post_json(rpc_url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if "error" in resp:
        raise RuntimeError(resp["error"])
    return resp.get("result")


def evm_get_decimals(rpc_url, token_address):
    result = evm_rpc_call(rpc_url, "eth_call", [{"to": token_address, "data": "0x313ce567"}, "latest"])
    return int(result, 16) if result else 18


def evm_pad_address_topic(address):
    return "0x" + address.lower().replace("0x", "").rjust(64, "0")


def evm_topic_to_address(topic):
    return "0x" + topic[-40:]


def evm_word_signed(data_hex, index):
    raw = data_hex[2:] if data_hex.startswith("0x") else data_hex
    word = raw[index * 64:(index + 1) * 64]
    value = int(word, 16)
    if value >= (1 << 255):
        value -= (1 << 256)
    return value


def watch_evm(ca, chain_id, pair_address, rpc_url, interval, emit, stop_event, tr):
    emit("info", tr.t("log_watching_evm", addr=pair_address))
    try:
        decimals = evm_get_decimals(rpc_url, ca)
    except Exception:
        decimals = 18
    try:
        last_block = int(evm_rpc_call(rpc_url, "eth_blockNumber", []), 16)
    except Exception as e:
        emit("error", tr.t("log_block_number_error", e=e))
        return

    pair_topic = evm_pad_address_topic(pair_address)

    while not stop_event.is_set():
        try:
            latest = int(evm_rpc_call(rpc_url, "eth_blockNumber", []), 16)
        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
            emit("error", tr.t("log_rpc_error", e=e, interval=interval))
            stop_event.wait(interval)
            continue

        if latest > last_block:
            try:
                logs = evm_rpc_call(rpc_url, "eth_getLogs", [{
                    "address": ca, "topics": [TRANSFER_TOPIC],
                    "fromBlock": hex(last_block + 1), "toBlock": hex(latest),
                }])
            except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
                emit("error", tr.t("log_eth_getlogs_error", e=e, interval=interval))
                stop_event.wait(interval)
                continue

            for lg in logs or []:
                topics = lg.get("topics") or []
                if len(topics) < 3:
                    continue
                from_topic, to_topic = topics[1], topics[2]
                amount = int(lg.get("data", "0x0"), 16) / (10 ** decimals)
                if from_topic.lower() != pair_topic.lower():
                    continue
                buyer = evm_topic_to_address(to_topic)
                tx_hash = lg.get("transactionHash")
                emit("trade", {
                    "time": time.strftime("%H:%M:%S"), "is_buy": True, "wallet": buyer,
                    "wallet_url": explorer_address_url(chain_id, buyer),
                    "amount": f"{amount:,.4f}", "amount_raw": amount,
                    "quote_amount": "", "quote_amount_raw": None, "quote_symbol": "",
                    "tx": tx_hash, "tx_url": explorer_tx_url(chain_id, tx_hash),
                })

            last_block = latest
        stop_event.wait(interval)


def find_uniswap_v4_pool_manager(rpc_url, token_address, lookback_blocks=100000, max_checked=60,
                                  chunk_blocks=5000):
    try:
        latest = int(evm_rpc_call(rpc_url, "eth_blockNumber", []), 16)
    except Exception:
        return None

    # сканируем чанками, а не одним широким запросом — на активных токенах один
    # запрос за lookback_blocks легко упирается в лимит RPC на число логов (10000)
    logs = []
    floor = max(0, latest - lookback_blocks)
    cur_to = latest
    while cur_to > floor:
        cur_from = max(floor, cur_to - chunk_blocks)
        try:
            batch = evm_rpc_call(rpc_url, "eth_getLogs", [{
                "address": token_address, "topics": [TRANSFER_TOPIC],
                "fromBlock": hex(cur_from), "toBlock": hex(cur_to),
            }])
            logs.extend(batch or [])
        except Exception:
            pass  # эту порцию пропускаем, но продолжаем сканировать дальше назад
        cur_to = cur_from - 1
        if len(logs) >= max_checked * 3:  # уже достаточно кандидатов, не тратим лимиты RPC зря
            break

    seen_tx = set()
    checked = 0
    for lg in reversed(logs or []):
        tx_hash = lg.get("transactionHash")
        if not tx_hash or tx_hash in seen_tx:
            continue
        seen_tx.add(tx_hash)
        if checked >= max_checked:
            break
        checked += 1
        try:
            receipt = evm_rpc_call(rpc_url, "eth_getTransactionReceipt", [tx_hash])
        except Exception:
            continue  # одиночный сбой RPC/rate-limit — пробуем следующую транзакцию
        for rl in (receipt or {}).get("logs", []):
            if rl.get("topics") and rl["topics"][0].lower() == UNISWAP_V4_SWAP_TOPIC.lower():
                return rl["address"]
    return None


_wallet_queue = queue.Queue()
_wallet_worker_lock = threading.Lock()
_wallet_worker_started = False


def _wallet_resolver_worker():
    """Один фоновый воркер на всё приложение: резолвит кошельки по очереди с паузой.
    Раньше на каждую сделку поднимался свой поток — на активном токене это давало
    залп параллельных запросов и ловило 429 от публичного RPC."""
    while True:
        rpc_url, chain_id, tx_hash, emit = _wallet_queue.get()
        wallet = "?"
        try:
            tx = evm_rpc_call(rpc_url, "eth_getTransactionByHash", [tx_hash])
            if tx and tx.get("from"):
                wallet = tx["from"]
        except Exception:
            pass
        emit("wallet_update", {
            "tx": tx_hash, "wallet": wallet,
            "wallet_url": explorer_address_url(chain_id, wallet) if wallet != "?" else "",
        })
        time.sleep(0.25)


def _resolve_wallet_async(rpc_url, chain_id, tx_hash, emit):
    """Ставит резолв кошелька в очередь — лента/цена/MCAP при этом не ждут."""
    global _wallet_worker_started
    with _wallet_worker_lock:
        if not _wallet_worker_started:
            threading.Thread(target=_wallet_resolver_worker, daemon=True).start()
            _wallet_worker_started = True
    _wallet_queue.put((rpc_url, chain_id, tx_hash, emit))


def watch_evm_v4(ca, chain_id, pool_manager, pool_id, quote_token_address, quote_symbol,
                  rpc_url, interval, emit, stop_event, tr):
    emit("info", tr.t("log_watching_v4", addr=pool_id))
    emit("info", tr.t("log_poolmanager_label", addr=pool_manager))
    try:
        decimals = evm_get_decimals(rpc_url, ca)
    except Exception:
        decimals = 18
    is_native_quote = int(quote_token_address, 16) == 0
    if is_native_quote:
        quote_decimals = 18
    else:
        try:
            quote_decimals = evm_get_decimals(rpc_url, quote_token_address)
        except Exception:
            quote_decimals = 18
    is_token0 = int(ca, 16) < int(quote_token_address, 16)
    try:
        last_block = int(evm_rpc_call(rpc_url, "eth_blockNumber", []), 16)
    except Exception as e:
        emit("error", tr.t("log_block_number_error", e=e))
        return

    backoff = interval
    max_backoff = max(interval * 10, 30)

    while not stop_event.is_set():
        try:
            latest = int(evm_rpc_call(rpc_url, "eth_blockNumber", []), 16)
        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
            emit("error", tr.t("log_rpc_error", e=e, interval=round(backoff, 1)))
            stop_event.wait(backoff)
            backoff = min(backoff * 2, max_backoff)
            continue

        if latest > last_block:
            try:
                logs = evm_rpc_call(rpc_url, "eth_getLogs", [{
                    "address": pool_manager, "topics": [UNISWAP_V4_SWAP_TOPIC, pool_id],
                    "fromBlock": hex(last_block + 1), "toBlock": hex(latest),
                }])
            except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
                emit("error", tr.t("log_eth_getlogs_error", e=e, interval=round(backoff, 1)))
                stop_event.wait(backoff)
                backoff = min(backoff * 2, max_backoff)
                continue

            backoff = interval  # успешный запрос — сбрасываем нарастающую паузу

            for lg in logs or []:
                amount0 = evm_word_signed(lg["data"], 0)
                amount1 = evm_word_signed(lg["data"], 1)
                our_amount = amount0 if is_token0 else amount1
                quote_amount_raw = amount1 if is_token0 else amount0
                # Uniswap V4 (в отличие от V3!) использует знак с точки зрения трейдера:
                # positive = трейдер ПОЛУЧАЕТ этот токен из пула (покупка),
                # negative = трейдер ОТДАЁТ его в пул (продажа).
                is_buy = our_amount > 0
                token_amount = abs(our_amount) / (10 ** decimals)
                quote_amount = abs(quote_amount_raw) / (10 ** quote_decimals)

                # Кошелёк требует ОТДЕЛЬНОГО RPC-запроса (eth_getTransactionByHash) —
                # в отличие от цены/суммы, которые уже есть прямо в логе. Раньше мы
                # ждали этот запрос (+ретраи с паузой) ПЕРЕД тем как показать сделку,
                # из-за чего цена/MCAP на экране отставали от реальной. Теперь сделка
                # показывается сразу, а кошелёк подтягивается в фоне и дополняется.
                tx_hash = lg["transactionHash"]
                emit("trade", {
                    "time": time.strftime("%H:%M:%S"), "is_buy": is_buy, "wallet": "…",
                    "wallet_url": "",
                    "amount": f"{token_amount:,.4f}", "amount_raw": token_amount,
                    "quote_amount": f"{quote_amount:,.4f}", "quote_amount_raw": quote_amount,
                    "quote_symbol": quote_symbol,
                    "tx": tx_hash, "tx_url": explorer_tx_url(chain_id, tx_hash),
                })
                _resolve_wallet_async(rpc_url, chain_id, tx_hash, emit)

            last_block = latest
        stop_event.wait(interval)


# ---------------------------------------------------------------------------
# Оркестратор
# ---------------------------------------------------------------------------

def run_watch(ca, interval, emit, stop_event, tr, rpc_override=None):
    ca = ca.strip()
    fmt = detect_chain_by_format(ca)
    if not fmt:
        emit("error", tr.t("log_invalid_ca"))
        return

    if fmt == "solana":
        emit("info", tr.t("log_checking_pumpfun", ca=ca))
        pf_info = fetch_pumpfun_info(ca)
        rpc_url = rpc_override or DEFAULT_SOLANA_RPC
        if pf_info and not pf_info.get("complete") and verify_pumpfun_curve(rpc_url, pf_info["bonding_curve"]):
            pf_decimals = pf_info.get("base_decimals", 6)
            mcap_anchor = pf_info.get("market_cap")
            price_native_anchor = None
            vsol = pf_info.get("virtual_sol_reserves")
            vtok = pf_info.get("virtual_token_reserves")
            if vsol and vtok:
                price_native_anchor = (vsol / 1e9) / (vtok / (10 ** pf_decimals))
            emit("meta", {
                "name": pf_info.get("name"), "symbol": pf_info.get("symbol"),
                "network": "Solana", "dex": tr.t("meta_source_pumpfun"),
                "price": "", "liquidity": f"{pf_info.get('market_cap', 0):,.2f} SOL (MC)",
                "mcap_anchor": mcap_anchor, "mcap_unit": " SOL", "mcap_unit_is_prefix": False,
                "price_native_anchor": price_native_anchor,
            })
            watch_pumpfun(ca, pf_info["bonding_curve"], pf_info["associated_bonding_curve"],
                          rpc_url, interval, pf_info.get("base_decimals", 6), emit, stop_event, tr)
            return

    emit("info", tr.t("log_checking_dexscreener"))
    try:
        info = fetch_dexscreener_info(ca)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        emit("error", tr.t("log_dexscreener_error", e=e))
        return

    if not info or not info.get("pairAddress"):
        emit("error", tr.t("log_no_pair"))
        return

    base = info["baseToken"]
    chain_id = (info.get("chainId") or "").lower()
    pair_address = info["pairAddress"]

    mcap_anchor = None
    price_native_anchor = None
    try:
        if info.get("marketCapUsd") and info.get("priceNative"):
            mcap_anchor = float(info["marketCapUsd"])
            price_native_anchor = float(info["priceNative"])
    except (TypeError, ValueError):
        pass

    emit("meta", {
        "name": base.get("name"), "symbol": base.get("symbol"),
        "network": chain_display_name(info["chainId"]), "dex": dex_display_name(info["dexId"]),
        "price": f"${info['priceUsd']}" if info.get("priceUsd") else "",
        "liquidity": f"${info['liquidityUsd']:,.0f}" if info.get("liquidityUsd") else "",
        "mcap_anchor": mcap_anchor, "mcap_unit": "$", "mcap_unit_is_prefix": True,
        "price_native_anchor": price_native_anchor,
    })

    if chain_id == "solana" or fmt == "solana":
        watch_solana(ca, pair_address, rpc_override or DEFAULT_SOLANA_RPC,
                     interval, emit, stop_event, tr)
    elif fmt == "evm":
        rpc_url = rpc_override or DEFAULT_EVM_RPCS.get(chain_id, DEFAULT_EVM_RPCS["ethereum"])
        if len(pair_address) == 66:
            emit("info", tr.t("log_v4_detected", chain=chain_id))
            pool_manager = find_uniswap_v4_pool_manager(rpc_url, ca)
            if not pool_manager:
                emit("error", tr.t("log_v4_poolmanager_not_found"))
                return
            quote_address = info["quoteToken"].get("address")
            quote_symbol = info["quoteToken"].get("symbol") or ""
            watch_evm_v4(ca, chain_id, pool_manager, pair_address, quote_address, quote_symbol,
                         rpc_url, interval, emit, stop_event, tr)
        else:
            watch_evm(ca, chain_id, pair_address, rpc_url, interval, emit, stop_event, tr)
    else:
        emit("error", tr.t("log_unknown_chain", chain=chain_id))


# ---------------------------------------------------------------------------
# GUI — тёмная тема в стиле трейдинг-терминалов
# ---------------------------------------------------------------------------

# Логотип приложения, вшит прямо в файл (base64 PNG 44x44),
# чтобы приложение оставалось одним файлом без внешних картинок.
LOGO_PNG_B64 = (
    "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"
)


BG = "#0a0c10"
PANEL = "#12151c"
PANEL2 = "#171b24"
BORDER = "#232733"
TEXT = "#e8e9ed"
MUTED = "#7d8493"
ACCENT = "#00d9ff"
ACCENT_HOVER = "#4de6ff"
GREEN = "#16c784"
GREEN_DIM = "#0f6b48"
RED = "#f6465d"
GOLD = "#ffb454"


def human_number(n):
    n = float(n)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1_000_000_000:
        return f"{sign}{n / 1_000_000_000:,.2f}B"
    if n >= 1_000_000:
        return f"{sign}{n / 1_000_000:,.2f}M"
    if n >= 1_000:
        return f"{sign}{n / 1_000:,.2f}K"
    return f"{sign}{n:,.2f}"


class App:
    def __init__(self, root):
        self.root = root
        self.tr = Translator("en")
        self.lang_var = tk.StringVar(value=LANG_NAMES["en"])

        root.title("XBIT888")
        root.geometry("1180x760")
        root.configure(bg=BG)
        root.minsize(980, 600)

        self._build_style()
        self._build_ui()

        self.log_queue = queue.Queue()
        self.stop_event = None
        self._bundle_stop_event = None
        self.worker = None
        self.meta_widgets = {}

        # живая статистика сессии
        self.buy_count = 0
        self.sell_count = 0
        self.buy_volume = 0.0
        self.sell_volume = 0.0
        self.quote_symbol = ""
        self.candles = []
        self.candle_seconds = 5
        self.mcap_anchor = None
        self.mcap_unit = ""
        self.mcap_unit_is_prefix = True
        self.price_native_anchor = None
        self._live_on = False
        self._live_blink_state = True

        self.root.after(120, self.drain_queue)
        self.root.after(500, self._blink_live_dot)
        self.root.after(1000, self._tick_clock)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.retranslate()

    # -- style ---------------------------------------------------------
    def _build_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)

        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 9))
        style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 8))
        style.configure("PanelValue.TLabel", background=PANEL, foreground=TEXT, font=("Consolas", 11, "bold"))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 16, "bold"))
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Status.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))

        style.configure("TEntry", fieldbackground=PANEL2, foreground=TEXT, insertcolor=TEXT,
                         bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=6)
        style.map("TEntry", fieldbackground=[("readonly", PANEL2)])

        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                         font=("Segoe UI", 10, "bold"), padding=(14, 8), borderwidth=0)
        style.map("Accent.TButton", background=[("active", ACCENT_HOVER), ("disabled", "#123a44")],
                  foreground=[("disabled", "#5a8a95")])

        style.configure("Stop.TButton", background=PANEL2, foreground=RED,
                         font=("Segoe UI", 10, "bold"), padding=(14, 8), borderwidth=1)
        style.map("Stop.TButton", background=[("active", "#1e1420"), ("disabled", PANEL2)],
                  foreground=[("disabled", "#5a4247")])

        style.configure("Ghost.TButton", background=BG, foreground=MUTED,
                         font=("Segoe UI", 9), padding=(10, 6), borderwidth=1)
        style.map("Ghost.TButton", background=[("active", PANEL)], foreground=[("active", TEXT)])

        style.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2, foreground=TEXT,
                         arrowcolor=TEXT, bordercolor=BORDER, padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL2)])

        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                         rowheight=26, font=("Consolas", 10), borderwidth=0)
        style.configure("Treeview.Heading", background=PANEL2, foreground=MUTED,
                         font=("Segoe UI", 9, "bold"), borderwidth=0, relief="flat")
        style.map("Treeview.Heading", background=[("active", PANEL2)])
        style.map("Treeview", background=[("selected", "#0f2933")], foreground=[("selected", TEXT)])

        style.configure("Vertical.TScrollbar", background=PANEL2, troughcolor=BG, bordercolor=BG,
                         arrowcolor=MUTED)

    # -- layout ----------------------------------------------------------
    def _build_ui(self):
        # ---- header: бренд, live-индикатор, быстрая статистика ----
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=18, pady=(14, 6))

        brand_wrap = tk.Frame(header, bg=BG)
        brand_wrap.pack(side="left")

        # логотип слева, название — правее него
        self.logo_img = None
        try:
            self.logo_img = tk.PhotoImage(data=LOGO_PNG_B64)
            tk.Label(brand_wrap, image=self.logo_img, bg=BG,
                     borderwidth=0, highlightthickness=0).pack(side="left", padx=(0, 12))
        except Exception:
            pass  # без логотипа приложение всё равно должно запускаться

        brand_box = tk.Frame(brand_wrap, bg=BG)
        brand_box.pack(side="left")
        brand_row = tk.Frame(brand_box, bg=BG)
        brand_row.pack(anchor="w")
        tk.Label(brand_row, text="XBIT", bg=BG, fg=TEXT, font=("Consolas", 20, "bold")).pack(side="left")
        tk.Label(brand_row, text="888", bg=BG, fg=ACCENT, font=("Consolas", 20, "bold")).pack(side="left")
        self.subtitle_lbl = tk.Label(brand_box, bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.subtitle_lbl.pack(anchor="w")

        # live-индикатор по центру
        live_box = tk.Frame(header, bg=BG)
        live_box.pack(side="left", expand=True)
        live_inner = tk.Frame(live_box, bg=BG)
        live_inner.place(relx=0.5, rely=0.5, anchor="center")
        self.live_dot = tk.Canvas(live_inner, width=12, height=12, bg=BG, highlightthickness=0)
        self._live_dot_id = self.live_dot.create_oval(2, 2, 10, 10, fill=MUTED, outline="")
        self.live_dot.pack(side="left", padx=(0, 6))
        self.live_lbl = tk.Label(live_inner, bg=BG, fg=MUTED, font=("Consolas", 11, "bold"))
        self.live_lbl.pack(side="left")

        # быстрая статистика справа
        stats_box = tk.Frame(header, bg=BG)
        stats_box.pack(side="right")
        self.header_buys_cap, self.header_buys_val = self._header_stat(stats_box, GREEN)
        self.header_sells_cap, self.header_sells_val = self._header_stat(stats_box, RED)
        self.header_clock_cap, self.header_clock_val = self._header_stat(stats_box, TEXT, last=True)

        lang_box = tk.Frame(header, bg=BG)
        lang_box.pack(side="right", padx=(0, 22))
        self.lang_lbl = tk.Label(lang_box, bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.lang_lbl.pack(anchor="e")
        self.lang_combo = ttk.Combobox(lang_box, textvariable=self.lang_var, state="readonly",
                                        values=[LANG_NAMES[c] for c in LANGS], width=6, justify="center")
        self.lang_combo.pack(anchor="e", pady=(2, 0))
        self.lang_combo.bind("<<ComboboxSelected>>", self.on_lang_change)

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", padx=18)

        # ---- input row ----
        input_row = ttk.Frame(self.root, padding=(18, 10, 18, 10))
        input_row.pack(fill="x")

        ca_col = ttk.Frame(input_row)
        ca_col.pack(side="left", fill="x", expand=True)
        self.ca_label_lbl = ttk.Label(ca_col, style="Muted.TLabel")
        self.ca_label_lbl.pack(anchor="w")
        self.ca_entry = ttk.Entry(ca_col, font=("Consolas", 11))
        self.ca_entry.pack(fill="x", pady=(2, 0))
        self.ca_entry.bind("<Return>", lambda e: self.start())

        rpc_col = ttk.Frame(input_row)
        rpc_col.pack(side="left", padx=(12, 0))
        self.rpc_label_lbl = ttk.Label(rpc_col, style="Muted.TLabel")
        self.rpc_label_lbl.pack(anchor="w")
        self.rpc_var = tk.StringVar(value="")
        ttk.Entry(rpc_col, textvariable=self.rpc_var, width=30, font=("Consolas", 10)).pack(pady=(2, 0))

        interval_col = ttk.Frame(input_row)
        interval_col.pack(side="left", padx=(12, 0))
        self.interval_label_lbl = ttk.Label(interval_col, style="Muted.TLabel")
        self.interval_label_lbl.pack(anchor="w")
        self.interval_var = tk.StringVar(value="1")
        ttk.Entry(interval_col, textvariable=self.interval_var, width=6, font=("Consolas", 11),
                  justify="center").pack(pady=(2, 0))

        btn_col = ttk.Frame(input_row)
        btn_col.pack(side="left", padx=(12, 0), anchor="s")
        self.start_btn = ttk.Button(btn_col, style="Accent.TButton", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(btn_col, style="Stop.TButton", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.clear_btn = ttk.Button(btn_col, style="Ghost.TButton", command=self.clear)
        self.clear_btn.pack(side="left")

        # ---- тело: три колонки ----
        body = ttk.Frame(self.root, padding=(18, 0, 18, 8))
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._build_token_card(body)
        self._build_bundle_card(body)   # центр — главное: анализ бандлов
        self._build_stats_card(body)

        # ---- второстепенная полоса: график + лента сделок ----
        self._build_bottom_strip()

        # ---- панель логов ----
        log_frame = ttk.Frame(self.root, padding=(18, 0, 18, 6))
        log_frame.pack(fill="x")
        self.log_text = tk.Text(log_frame, height=4, bg=PANEL, fg=MUTED, insertbackground=TEXT,
                                 font=("Consolas", 9), relief="flat", wrap="word", state="disabled")
        self.log_text.pack(fill="x")
        self.log_text.tag_config("error", foreground=GOLD)
        self.log_text.tag_config("info", foreground=MUTED)

        # ---- статус-бар ----
        status_bar = ttk.Frame(self.root, padding=(18, 4, 18, 10))
        status_bar.pack(fill="x")
        self.status_var = tk.StringVar()
        ttk.Label(status_bar, textvariable=self.status_var, style="Status.TLabel").pack(side="left")
        self.hint_lbl = ttk.Label(status_bar, style="Muted.TLabel")
        self.hint_lbl.pack(side="right")

        self._row_count = 0
        self._row_data = {}  # iid -> {"wallet_url":..., "wallet":..., "tx_url":...}
        self._tx_to_row = {}  # tx hash -> iid, для фонового дозаполнения кошелька

    def _header_stat(self, parent, color, last=False):
        box = tk.Frame(parent, bg=BG)
        box.pack(side="left", padx=(0, 0) if last else (0, 22))
        cap = tk.Label(box, bg=BG, fg=MUTED, font=("Segoe UI", 8, "bold"))
        cap.pack(anchor="e")
        val = tk.Label(box, text="0", bg=BG, fg=color, font=("Consolas", 13, "bold"))
        val.pack(anchor="e")
        return cap, val

    def _card(self, parent, col, minwidth=None, weight=0):
        outer = tk.Frame(parent, bg=BORDER)
        outer.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 0 if col == 2 else 8))
        if minwidth:
            outer.grid_propagate(False)
            outer.configure(width=minwidth)
        parent.grid_columnconfigure(col, weight=weight)
        inner = tk.Frame(outer, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        return inner

    def _build_token_card(self, parent):
        card = self._card(parent, 0, minwidth=250)
        pad = tk.Frame(card, bg=PANEL, padx=14, pady=12)
        pad.pack(fill="both", expand=True)

        self.token_card_title = tk.Label(pad, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"))
        self.token_card_title.pack(anchor="w")

        id_row = tk.Frame(pad, bg=PANEL)
        id_row.pack(fill="x", pady=(10, 12))
        self.token_icon = tk.Label(id_row, text="?", width=3, bg=ACCENT, fg="#ffffff",
                                    font=("Segoe UI", 12, "bold"))
        self.token_icon.pack(side="left")
        name_box = tk.Frame(id_row, bg=PANEL)
        name_box.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self.token_name_lbl = tk.Label(name_box, text="—", bg=PANEL, fg=TEXT,
                                        font=("Segoe UI", 12, "bold"), anchor="w")
        self.token_name_lbl.pack(fill="x")
        self.token_symbol_lbl = tk.Label(name_box, text="", bg=PANEL, fg=MUTED,
                                          font=("Segoe UI", 9), anchor="w")
        self.token_symbol_lbl.pack(fill="x")

        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=(0, 10))

        self.token_rows = {}
        for key, field in [("row_network", "network"), ("row_dex", "dex"),
                            ("row_price", "price"), ("row_liquidity", "liquidity")]:
            row = tk.Frame(pad, bg=PANEL)
            row.pack(fill="x", pady=4)
            cap = tk.Label(row, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"), anchor="w")
            cap.pack(anchor="w")
            val = tk.Label(row, text="—", bg=PANEL, fg=TEXT, font=("Consolas", 11, "bold"), anchor="w")
            val.pack(anchor="w")
            self.token_rows[field] = (key, cap, val)
        self.meta_labels = self.token_rows  # обратная совместимость с update_meta()

        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=(4, 10))
        bundle_row = tk.Frame(pad, bg=PANEL)
        bundle_row.pack(fill="x")
        self.bundle_row_cap = tk.Label(bundle_row, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"), anchor="w")
        self.bundle_row_cap.pack(anchor="w")
        self.bundle_row_val = tk.Label(bundle_row, text="—", bg=PANEL, fg=TEXT,
                                        font=("Consolas", 11, "bold"), anchor="w")
        self.bundle_row_val.pack(anchor="w")

    def _build_bundle_card(self, parent):
        """Главная панель приложения — результат анализа бандлов."""
        card = self._card(parent, 1, weight=1)
        pad = tk.Frame(card, bg=PANEL, padx=16, pady=14)
        pad.pack(fill="both", expand=True)

        head = tk.Frame(pad, bg=PANEL)
        head.pack(fill="x")
        self.bundle_card_title = tk.Label(head, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"))
        self.bundle_card_title.pack(side="left")
        self.bundle_window_lbl = tk.Label(head, bg=PANEL, fg=MUTED, font=("Segoe UI", 8))
        self.bundle_window_lbl.pack(side="right")

        self.bundle_big_val = tk.Label(pad, text="—", bg=PANEL, fg=TEXT,
                                        font=("Consolas", 40, "bold"), anchor="w")
        self.bundle_big_val.pack(anchor="w", pady=(12, 0))
        self.bundle_verdict_lbl = tk.Label(pad, text="", bg=PANEL, fg=MUTED,
                                            font=("Segoe UI", 11, "bold"), anchor="w")
        self.bundle_verdict_lbl.pack(anchor="w")
        self.bundle_early_lbl = tk.Label(pad, text="", bg=PANEL, fg=MUTED,
                                          font=("Consolas", 9), anchor="w")
        self.bundle_early_lbl.pack(anchor="w", pady=(8, 0))

        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=12)

        table_frame = tk.Frame(pad, bg=PANEL)
        table_frame.pack(fill="both", expand=True)
        cols = ("funder", "wallets", "pct")
        self.bundle_tree = ttk.Treeview(table_frame, columns=cols, show="headings", style="Treeview")
        self.bundle_tree.column("funder", width=240, anchor="w", stretch=True)
        self.bundle_tree.column("wallets", width=90, anchor="center", stretch=False)
        self.bundle_tree.column("pct", width=120, anchor="e", stretch=False)
        self.bundle_tree.tag_configure("bundle", foreground=RED, background="#2a1116")
        self.bundle_tree.bind("<Double-Button-1>", self.on_bundle_row_double_click)
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.bundle_tree.yview)
        self.bundle_tree.configure(yscrollcommand=vsb.set)
        self.bundle_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._bundle_row_data = {}

    def _build_bottom_strip(self):
        """Второстепенная полоса: компактный график цены + компактная лента сделок."""
        strip = ttk.Frame(self.root, padding=(18, 0, 18, 6))
        strip.pack(fill="x")
        strip.grid_columnconfigure(0, weight=2, uniform="strip")
        strip.grid_columnconfigure(1, weight=3, uniform="strip")

        chart_outer = tk.Frame(strip, bg=BORDER)
        chart_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        chart_card = tk.Frame(chart_outer, bg=PANEL)
        chart_card.pack(fill="both", expand=True, padx=1, pady=1)

        chart_head = tk.Frame(chart_card, bg=PANEL, padx=10, pady=6)
        chart_head.pack(fill="x")
        self.feed_card_title = tk.Label(chart_head, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"))
        self.feed_card_title.pack(side="left")
        price_box = tk.Frame(chart_head, bg=PANEL)
        price_box.pack(side="right")
        self.last_price_cap = tk.Label(price_box, bg=PANEL, fg=MUTED, font=("Segoe UI", 7, "bold"), anchor="e")
        self.last_price_cap.pack(anchor="e")
        self.last_price_val = tk.Label(price_box, text="—", bg=PANEL, fg=GREEN,
                                        font=("Consolas", 13, "bold"), anchor="e")
        self.last_price_val.pack(anchor="e")

        self.spark_canvas = tk.Canvas(chart_card, bg=PANEL, height=120, highlightthickness=0)
        self.spark_canvas.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.spark_placeholder = self.spark_canvas.create_text(
            10, 60, anchor="w", fill=MUTED, font=("Segoe UI", 9), text=""
        )
        self.spark_canvas.bind("<Configure>", lambda e: self._redraw_candles())

        feed_outer = tk.Frame(strip, bg=BORDER)
        feed_outer.grid(row=0, column=1, sticky="nsew")
        feed_card = tk.Frame(feed_outer, bg=PANEL)
        feed_card.pack(fill="both", expand=True, padx=1, pady=1)

        feed_head = tk.Frame(feed_card, bg=PANEL, padx=10, pady=6)
        feed_head.pack(fill="x")
        self.trades_title = tk.Label(feed_head, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"))
        self.trades_title.pack(side="left")

        table_frame = tk.Frame(feed_card, bg=PANEL)
        table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        columns = ("time", "type", "wallet", "amount", "value", "tx")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings",
                                  style="Treeview", height=6)
        for col, w, anchor in [
            ("time", 62, "center"), ("type", 78, "center"), ("wallet", 130, "w"),
            ("amount", 110, "e"), ("value", 90, "e"), ("tx", 110, "w"),
        ]:
            self.tree.column(col, width=w, anchor=anchor, stretch=(col in ("wallet", "tx")))
        self.tree.tag_configure("buy", foreground=GREEN, background="#0f2419")
        self.tree.tag_configure("sell", foreground=RED, background="#2a1116")
        self.tree.bind("<Double-Button-1>", self.on_row_double_click)
        self.tree.bind("<Motion>", self.on_row_hover)

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    def _build_stats_card(self, parent):
        card = self._card(parent, 2, minwidth=220)
        pad = tk.Frame(card, bg=PANEL, padx=14, pady=12)
        pad.pack(fill="both", expand=True)

        self.stats_card_title = tk.Label(pad, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"))
        self.stats_card_title.pack(anchor="w")
        self.stats_hint_lbl = tk.Label(pad, bg=PANEL, fg=MUTED, font=("Segoe UI", 7), anchor="w",
                                        wraplength=190, justify="left")
        self.stats_hint_lbl.pack(anchor="w", pady=(2, 0))

        big_row = tk.Frame(pad, bg=PANEL)
        big_row.pack(fill="x", pady=(14, 10))

        buy_box = tk.Frame(big_row, bg=PANEL)
        buy_box.pack(side="left", expand=True, fill="x")
        self.stats_buys_val = tk.Label(buy_box, text="0", bg=PANEL, fg=GREEN, font=("Consolas", 26, "bold"))
        self.stats_buys_val.pack(anchor="w")
        self.stats_buys_cap = tk.Label(buy_box, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"), anchor="w")
        self.stats_buys_cap.pack(anchor="w")

        sell_box = tk.Frame(big_row, bg=PANEL)
        sell_box.pack(side="left", expand=True, fill="x")
        self.stats_sells_val = tk.Label(sell_box, text="0", bg=PANEL, fg=RED, font=("Consolas", 26, "bold"))
        self.stats_sells_val.pack(anchor="w")
        self.stats_sells_cap = tk.Label(sell_box, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"), anchor="w")
        self.stats_sells_cap.pack(anchor="w")

        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=(4, 10))

        self.stat_buy_vol_cap = tk.Label(pad, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"), anchor="w")
        self.stat_buy_vol_cap.pack(anchor="w")
        self.stat_buy_vol_val = tk.Label(pad, text="—", bg=PANEL, fg=GREEN, font=("Consolas", 12, "bold"), anchor="w")
        self.stat_buy_vol_val.pack(anchor="w", pady=(0, 8))

        self.stat_sell_vol_cap = tk.Label(pad, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"), anchor="w")
        self.stat_sell_vol_cap.pack(anchor="w")
        self.stat_sell_vol_val = tk.Label(pad, text="—", bg=PANEL, fg=RED, font=("Consolas", 12, "bold"), anchor="w")
        self.stat_sell_vol_val.pack(anchor="w", pady=(0, 8))

        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=(4, 10))

        self.stat_net_cap = tk.Label(pad, bg=PANEL, fg=MUTED, font=("Segoe UI", 8, "bold"), anchor="w")
        self.stat_net_cap.pack(anchor="w")
        self.stat_net_val = tk.Label(pad, text="—", bg=PANEL, fg=TEXT, font=("Consolas", 15, "bold"), anchor="w")
        self.stat_net_val.pack(anchor="w")
        self.stat_net_hint = tk.Label(pad, bg=PANEL, fg=MUTED, font=("Segoe UI", 7), anchor="w",
                                       wraplength=190, justify="left")
        self.stat_net_hint.pack(anchor="w", pady=(2, 0))

    # -- i18n ------------------------------------------------------------
    def on_lang_change(self, _evt=None):
        code_by_name = {v: k for k, v in LANG_NAMES.items()}
        self.tr.lang = code_by_name.get(self.lang_var.get(), "ru")
        self.retranslate()

    def retranslate(self):
        t = self.tr.t
        self.root.title(t("app_title"))
        if not self.worker:
            self.subtitle_lbl.configure(text=t("app_subtitle"))
        self.lang_lbl.configure(text=t("lang_label"))
        self.ca_label_lbl.configure(text=t("ca_label"))
        self.interval_label_lbl.configure(text=t("interval_label"))
        self.start_btn.configure(text=t("start"))
        self.stop_btn.configure(text=t("stop"))
        self.clear_btn.configure(text=t("clear"))
        self.bundle_row_cap.configure(text=t("row_bundle"))
        if not self.worker:
            self.bundle_row_val.configure(text="—")
        self.status_var.set(t("status_ready") if not self.worker else t("status_running"))

        self.live_lbl.configure(text=t("live") if self._live_on else t("offline"))
        self.header_buys_cap.configure(text=t("header_stat_buys"))
        self.header_sells_cap.configure(text=t("header_stat_sells"))
        self.header_clock_cap.configure(text=t("header_stat_clock"))

        self.token_card_title.configure(text=t("card_token_info"))
        self.feed_card_title.configure(text=t("card_live_feed"))
        self.stats_card_title.configure(text=t("card_live_stats"))
        self.bundle_card_title.configure(text=t("card_bundle_analysis"))
        self.trades_title.configure(text=t("card_trades"))
        self.bundle_window_lbl.configure(text=t("bundle_window_fmt", w=BUNDLE_WINDOW_SECONDS))
        self.bundle_tree.heading("funder", text=t("col_funder"))
        self.bundle_tree.heading("wallets", text=t("col_wallets"))
        self.bundle_tree.heading("pct", text=t("col_supply_pct"))
        self.last_price_cap.configure(text=t("last_price_label"))
        self.stats_buys_cap.configure(text=t("header_stat_buys"))
        self.stats_sells_cap.configure(text=t("header_stat_sells"))
        self.stats_hint_lbl.configure(text=t("stats_hint"))
        self.stat_net_hint.configure(text=t("stat_net_hint"))
        self.rpc_label_lbl.configure(text=t("rpc_label"))
        self.stat_buy_vol_cap.configure(text=t("stat_buy_volume"))
        self.stat_sell_vol_cap.configure(text=t("stat_sell_volume"))
        self.stat_net_cap.configure(text=t("stat_net_flow"))

        self.tree.heading("time", text=t("col_time"))
        self.tree.heading("type", text=t("col_type"))
        self.tree.heading("wallet", text=t("col_wallet"))
        self.tree.heading("amount", text=t("col_amount"))
        self.tree.heading("value", text=t("col_value"))
        self.tree.heading("tx", text=t("col_tx"))
        self.hint_lbl.configure(text=t("hint_click"))

        for field, (key, cap, val) in self.token_rows.items():
            cap.configure(text=t(key))

        if not self.candles:
            self.spark_canvas.itemconfigure(self.spark_placeholder, text=t("no_chart_data"))

        # перевод уже вставленных строк типа BUY/SELL в таблице
        for row_id in self.tree.get_children():
            vals = list(self.tree.item(row_id, "values"))
            tags = self.tree.item(row_id, "tags")
            if "buy" in tags:
                vals[1] = "▲ " + t("trade_buy")
            elif "sell" in tags:
                vals[1] = "▼ " + t("trade_sell")
            self.tree.item(row_id, values=vals)

    # -- queue / events ----------------------------------------------------
    def emit(self, kind, payload):
        self.log_queue.put((kind, payload))

    def drain_queue(self):
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "stopped":
                    self.start_btn.configure(state="normal")
                    self.ca_entry.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self.status_var.set(self.tr.t("status_stopped"))
                    self._live_on = False
                    self.live_lbl.configure(text=self.tr.t("offline"))
                elif kind == "meta":
                    self.update_meta(payload)
                elif kind == "trade":
                    self.add_trade_row(payload)
                elif kind == "wallet_update":
                    self.update_trade_wallet(payload)
                elif kind == "bundle_result":
                    self.show_bundle_result(payload)
                elif kind in ("info", "error"):
                    self.status_var.set(str(payload))
                    self.append_log(str(payload), kind)
        except queue.Empty:
            pass
        self.root.after(120, self.drain_queue)

    def append_log(self, text, tag):
        self.log_text.configure(state="normal")
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {text}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def update_meta(self, data):
        name = data.get("name") or ""
        symbol = data.get("symbol") or ""
        self.token_name_lbl.configure(text=name or "—")
        self.token_symbol_lbl.configure(text=symbol or "")
        self.token_icon.configure(text=(symbol or name or "?")[:1].upper())
        values = {
            "network": data.get("network") or "—",
            "dex": data.get("dex") or "—",
            "price": data.get("price") or "—",
            "liquidity": data.get("liquidity") or "—",
        }
        for field, (key, cap, val) in self.token_rows.items():
            val.configure(text=values.get(field, "—"))

        self.mcap_anchor = data.get("mcap_anchor")
        self.mcap_unit = data.get("mcap_unit") or ""
        self.mcap_unit_is_prefix = data.get("mcap_unit_is_prefix", True)
        self.price_native_anchor = data.get("price_native_anchor")

        # показываем капитализацию и стартовую точку графика сразу, не дожидаясь первой live-сделки
        if self.mcap_anchor:
            self.last_price_val.configure(text=self._format_mcap(self.mcap_anchor), fg=TEXT)
        if self.price_native_anchor and not self.candles:
            self._add_candle_point(self.price_native_anchor)
            self._redraw_candles()

        parts = [p for p in [name, data.get("network"), data.get("dex")] if p]
        if parts:
            self.subtitle_lbl.configure(text="  ·  ".join(parts))

    def _format_mcap(self, value):
        text = human_number(value)
        return f"{self.mcap_unit}{text}" if self.mcap_unit_is_prefix else f"{text}{self.mcap_unit}"

    def update_trade_wallet(self, data):
        """Дозаполняет кошелёк, который резолвился в фоне отдельным запросом
        (используется для Uniswap V4 — там кошелёк не лежит прямо в логе)."""
        row_id = self._tx_to_row.get(data.get("tx"))
        if not row_id or not self.tree.exists(row_id):
            return
        wallet = data.get("wallet") or "?"
        wallet_short = wallet if len(wallet) <= 20 else f"{wallet[:10]}…{wallet[-6:]}"
        vals = list(self.tree.item(row_id, "values"))
        vals[2] = wallet_short
        self.tree.item(row_id, values=vals)
        if row_id in self._row_data:
            self._row_data[row_id]["wallet"] = wallet
            self._row_data[row_id]["wallet_url"] = data.get("wallet_url") or wallet

    def add_trade_row(self, data):
        t = self.tr.t
        is_buy = data["is_buy"]
        tag_type = "buy" if is_buy else "sell"
        arrow = "▲" if is_buy else "▼"
        label = f"{arrow} " + (t("trade_buy") if is_buy else t("trade_sell"))
        self._row_count += 1

        wallet = data["wallet"]
        wallet_short = wallet if len(wallet) <= 20 else f"{wallet[:10]}…{wallet[-6:]}"
        tx_short = data["tx"] if len(data["tx"]) <= 22 else f"{data['tx'][:10]}…{data['tx'][-6:]}"
        quote_amount = data.get("quote_amount") or ""
        quote_symbol = data.get("quote_symbol") or ""
        value_text = f"{quote_amount} {quote_symbol}".strip() if quote_amount else "—"

        row_id = self.tree.insert(
            "", 0,
            values=(data["time"], label, wallet_short, data["amount"], value_text, tx_short),
            tags=(tag_type,),
        )
        self._row_data[row_id] = {
            "wallet": wallet,
            "wallet_url": data.get("wallet_url") or wallet,
            "tx_url": data.get("tx_url") or data["tx"],
        }
        self._tx_to_row[data["tx"]] = row_id

        # ограничиваем размер таблицы, чтобы GUI не разрастался бесконечно
        children = self.tree.get_children()
        if len(children) > 500:
            removed_ids = set(children[500:])
            for old_id in removed_ids:
                self.tree.delete(old_id)
                self._row_data.pop(old_id, None)
            self._tx_to_row = {tx: rid for tx, rid in self._tx_to_row.items() if rid not in removed_ids}

        # -- живая статистика и график --
        amount_raw = data.get("amount_raw")
        quote_raw = data.get("quote_amount_raw")
        symbol = data.get("quote_symbol") or ""
        if symbol:
            self.quote_symbol = symbol

        if is_buy:
            self.buy_count += 1
            if quote_raw:
                self.buy_volume += quote_raw
        else:
            self.sell_count += 1
            if quote_raw:
                self.sell_volume += quote_raw

        self.header_buys_val.configure(text=f"{self.buy_count:,}")
        self.header_sells_val.configure(text=f"{self.sell_count:,}")
        self.stats_buys_val.configure(text=f"{self.buy_count:,}")
        self.stats_sells_val.configure(text=f"{self.sell_count:,}")

        if self.buy_volume or self.sell_volume:
            self.stat_buy_vol_val.configure(text=f"{self.buy_volume:,.4f} {self.quote_symbol}".strip())
            self.stat_sell_vol_val.configure(text=f"{self.sell_volume:,.4f} {self.quote_symbol}".strip())
            net = self.buy_volume - self.sell_volume
            net_color = GREEN if net >= 0 else RED
            sign = "+" if net >= 0 else ""
            self.stat_net_val.configure(text=f"{sign}{net:,.4f} {self.quote_symbol}".strip(), fg=net_color)

        if quote_raw and amount_raw:
            try:
                price = quote_raw / amount_raw
                self._add_candle_point(price)
                if self.mcap_anchor and self.price_native_anchor:
                    ratio = price / self.price_native_anchor
                    live_mcap = self.mcap_anchor * ratio
                    self.last_price_val.configure(text=self._format_mcap(live_mcap),
                                                   fg=GREEN if is_buy else RED)
                else:
                    self.last_price_val.configure(text=f"{price:,.10f}".rstrip("0").rstrip("."),
                                                   fg=GREEN if is_buy else RED)
                self._redraw_candles()
            except ZeroDivisionError:
                pass

    def _add_candle_point(self, price):
        """Группирует поступающие цены в свечи по интервалу CANDLE_SECONDS —
        как на настоящем графике, а не просто линия цена-от-времени."""
        bucket = int(time.time() // self.candle_seconds)
        if self.candles and self.candles[-1]["bucket"] == bucket:
            c = self.candles[-1]
            c["high"] = max(c["high"], price)
            c["low"] = min(c["low"], price)
            c["close"] = price
        else:
            self.candles.append({
                "bucket": bucket, "open": price, "high": price, "low": price, "close": price,
            })
            if len(self.candles) > 60:
                self.candles = self.candles[-60:]

    def _redraw_candles(self):
        c = self.spark_canvas
        c.delete("candle")
        w = c.winfo_width() or 400
        h = c.winfo_height() or 130
        candles = self.candles
        if not candles:
            c.itemconfigure(self.spark_placeholder, text=self.tr.t("no_chart_data"))
            c.coords(self.spark_placeholder, 10, h // 2)
            return
        c.itemconfigure(self.spark_placeholder, text="")

        lo = min(cd["low"] for cd in candles)
        hi = max(cd["high"] for cd in candles)
        span = (hi - lo) or (hi * 0.01 or 1)
        pad_y = 8
        pad_x = 6
        slot = (w - 2 * pad_x) / len(candles)
        body_w = max(3, min(slot * 0.62, 18))

        def y_of(v):
            return h - pad_y - (v - lo) / span * (h - 2 * pad_y)

        for frac in (0.0, 0.5, 1.0):  # лёгкая сетка, чтобы график не висел в пустоте
            gy = pad_y + frac * (h - 2 * pad_y)
            c.create_line(pad_x, gy, w - pad_x, gy, fill=BORDER, tags="candle")

        for i, cd in enumerate(candles):
            x = pad_x + i * slot + slot / 2
            up = cd["close"] >= cd["open"]
            color = GREEN if up else RED
            c.create_line(x, y_of(cd["high"]), x, y_of(cd["low"]), fill=color, width=1, tags="candle")
            top = y_of(max(cd["open"], cd["close"]))
            bottom = y_of(min(cd["open"], cd["close"]))
            c.create_rectangle(x - body_w / 2, top, x + body_w / 2, max(bottom, top + 1),
                                fill=color, outline=color, tags="candle")

    def _blink_live_dot(self):
        if self._live_on:
            self._live_blink_state = not self._live_blink_state
            color = GREEN if self._live_blink_state else GREEN_DIM
            self.live_dot.itemconfigure(self._live_dot_id, fill=color)
            self.live_lbl.configure(fg=GREEN)
        else:
            self.live_dot.itemconfigure(self._live_dot_id, fill=MUTED)
            self.live_lbl.configure(fg=MUTED)
        self.root.after(600, self._blink_live_dot)

    def _tick_clock(self):
        self.header_clock_val.configure(text=time.strftime("%H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    def on_row_hover(self, event):
        region = self.tree.identify_region(event.x, event.y)
        col = self.tree.identify_column(event.x) if region == "cell" else None
        if col in ("#3", "#6"):  # wallet, tx
            self.tree.configure(cursor="hand2")
        else:
            self.tree.configure(cursor="")

    def on_row_double_click(self, event):
        row_id = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not row_id or row_id not in self._row_data:
            return
        info = self._row_data[row_id]
        if col == "#3":  # wallet
            self.root.clipboard_clear()
            self.root.clipboard_append(info["wallet"])
            self.status_var.set(self.tr.t("copied", value=info["wallet"]))
        elif col == "#6":  # tx
            webbrowser.open(info["tx_url"])

    # -- actions -----------------------------------------------------------
    def clear(self):
        for row_id in self.tree.get_children():
            self.tree.delete(row_id)
        self._row_count = 0
        self._row_data.clear()
        self._tx_to_row.clear()
        self.clear_log()

        self.buy_count = 0
        self.sell_count = 0
        self.buy_volume = 0.0
        self.sell_volume = 0.0
        self.quote_symbol = ""
        self.candles = []
        self.mcap_anchor = None
        self.mcap_unit = ""
        self.mcap_unit_is_prefix = True
        self.price_native_anchor = None
        self.header_buys_val.configure(text="0")
        self.header_sells_val.configure(text="0")
        self.stats_buys_val.configure(text="0")
        self.stats_sells_val.configure(text="0")
        self.stat_buy_vol_val.configure(text="—")
        self.stat_sell_vol_val.configure(text="—")
        self.stat_net_val.configure(text="—", fg=TEXT)
        self.last_price_val.configure(text="—", fg=GREEN)
        self.bundle_row_val.configure(text="—", fg=TEXT)
        self.bundle_big_val.configure(text="—", fg=TEXT)
        self.bundle_verdict_lbl.configure(text="", fg=MUTED)
        self.bundle_early_lbl.configure(text="")
        self.clear_bundle_table()
        self._redraw_candles()

    def start(self):
        ca = self.ca_entry.get().strip()
        if not ca:
            self.status_var.set(self.tr.t("status_enter_ca"))
            return
        rpc_override = self.rpc_var.get().strip() or None
        # на публичном RPC меньше 0.5с смысла нет — упрёмся в лимиты и станет только
        # медленнее; со своим эндпоинтом можно опускаться до 0.1с
        floor = 0.1 if rpc_override else 0.5
        try:
            interval = max(floor, float(self.interval_var.get()))
        except ValueError:
            interval = 1.0

        self.clear()
        for field, (key, cap, val) in self.token_rows.items():
            val.configure(text="—")
        self.token_name_lbl.configure(text="—")
        self.token_symbol_lbl.configure(text="")
        self.token_icon.configure(text="?")

        self.stop_event = threading.Event()
        self.start_btn.configure(state="disabled")
        self.ca_entry.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_var.set(self.tr.t("status_running"))
        self._live_on = True
        self.live_lbl.configure(text=self.tr.t("live"))

        tr = self.tr
        stop_event = self.stop_event

        def worker():
            try:
                run_watch(ca, interval, self.emit, stop_event, tr, rpc_override=rpc_override)
            except Exception as e:
                self.emit("error", tr.t("log_unexpected_error", e=e))
            finally:
                self.emit("stopped", None)

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

        # бандл-проверка — главная функция, запускается сразу вместе со стартом
        self.start_bundle_check(ca, rpc_override)

    def stop(self):
        if self.stop_event:
            self.stop_event.set()
        if self._bundle_stop_event:
            self._bundle_stop_event.set()
        self.worker = None
        self._live_on = False
        self.live_lbl.configure(text=self.tr.t("offline"))
        self.status_var.set(self.tr.t("status_stopped"))
        self.start_btn.configure(state="normal")
        self.ca_entry.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    def start_bundle_check(self, ca, rpc_override=None):
        if self._bundle_stop_event:
            self._bundle_stop_event.set()  # прерываем предыдущую проверку, если ещё бежит

        self._bundle_stop_event = threading.Event()
        bundle_stop_event = self._bundle_stop_event
        tr = self.tr

        self.bundle_row_val.configure(text=tr.t("bundle_checking_short"), fg=MUTED)
        self.bundle_big_val.configure(text="…", fg=MUTED)
        self.bundle_verdict_lbl.configure(text=tr.t("bundle_verdict_checking"), fg=MUTED)
        self.bundle_early_lbl.configure(text="")
        self.clear_bundle_table()

        def worker():
            try:
                run_bundle_check(ca, self.emit, tr, bundle_stop_event, rpc_override=rpc_override)
            except Exception as e:
                self.emit("bundle_result", {"error": tr.t("log_unexpected_error", e=e)})

        threading.Thread(target=worker, daemon=True).start()

    def clear_bundle_table(self):
        for row_id in self.bundle_tree.get_children():
            self.bundle_tree.delete(row_id)
        self._bundle_row_data.clear()

    def show_bundle_result(self, data):
        t = self.tr.t
        self.clear_bundle_table()

        if data.get("error"):
            self.append_log(data["error"], "error")
            self.bundle_row_val.configure(text=t("bundle_row_na"), fg=MUTED)
            self.bundle_big_val.configure(text="—", fg=MUTED)
            self.bundle_verdict_lbl.configure(text=t("bundle_verdict_na"), fg=MUTED)
            self.bundle_early_lbl.configure(text=str(data["error"]))
            return

        self.append_log(f"— {t('bundle_result_title')} —", "info")
        self.append_log(
            t("bundle_result_early", window=data["window_seconds"],
              pct=data["early_pct"], wallets=data["early_wallets"]),
            "info",
        )
        self.bundle_early_lbl.configure(
            text=t("bundle_early_fmt", pct=data["early_pct"], wallets=data["early_wallets"]))

        if data.get("funder_unsupported"):
            self.append_log(t("bundle_funder_unsupported_note"), "info")
            self.bundle_row_val.configure(
                text=t("bundle_row_early_only", pct=data["early_pct"]), fg=TEXT)
            self.bundle_big_val.configure(text=f"{data['early_pct']:.1f}%", fg=GOLD)
            self.bundle_verdict_lbl.configure(text=t("bundle_verdict_early_only"), fg=GOLD)
            return

        clusters = data.get("bundle_clusters") or {}
        if clusters:
            self.append_log(t("bundle_result_bundled", pct=data["bundle_pct"]), "error")
            self.bundle_big_val.configure(text=f"{data['bundle_pct']:.1f}%", fg=RED)
            self.bundle_verdict_lbl.configure(text=t("bundle_verdict_bundled"), fg=RED)
            self.bundle_row_val.configure(
                text=t("bundle_row_bundled", pct=data["bundle_pct"]), fg=RED)

            for funder, info in sorted(clusters.items(), key=lambda kv: kv[1]["amount"], reverse=True):
                short_funder = funder if len(funder) <= 20 else f"{funder[:10]}…{funder[-6:]}"
                self.append_log(
                    t("bundle_result_cluster", n=len(info["wallets"]), funder=short_funder, pct=info["pct"]),
                    "error",
                )
                row_id = self.bundle_tree.insert(
                    "", "end",
                    values=(short_funder, len(info["wallets"]), f"{info['pct']:.2f}%"),
                    tags=("bundle",),
                )
                self._bundle_row_data[row_id] = {"funder": funder, "wallets": info["wallets"]}
        else:
            self.append_log(t("bundle_result_none"), "info")
            self.bundle_big_val.configure(text="0.0%", fg=GREEN)
            self.bundle_verdict_lbl.configure(text=t("bundle_verdict_clean"), fg=GREEN)
            self.bundle_row_val.configure(text=t("bundle_row_clean"), fg=GREEN)

        if data.get("truncated"):
            self.append_log(t("bundle_result_cap_note", n=25), "info")

    def on_bundle_row_double_click(self, event):
        row_id = self.bundle_tree.identify_row(event.y)
        info = self._bundle_row_data.get(row_id)
        if not info:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(info["funder"])
        self.status_var.set(self.tr.t("copied", value=info["funder"]))

    def on_close(self):
        if self.stop_event:
            self.stop_event.set()
        if self._bundle_stop_event:
            self._bundle_stop_event.set()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
