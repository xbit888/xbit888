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
import os
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
    "ca_placeholder": {"ru": "вставьте адрес токена с GMGN и нажмите Старт",
                        "en": "paste a token address from GMGN and press Start",
                        "zh": "粘贴 GMGN 上的代币地址后点击开始"},
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
    "log_rpc_discovery": {
        "ru": "Dexscreener токен ещё не знает — ищу пул напрямую в блокчейне...",
        "en": "Dexscreener doesn't know this token yet — looking for the pool on-chain...",
        "zh": "Dexscreener 尚未收录该代币——正在链上直接查找资金池..."},
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
    "log_rpc_throttled": {
        "ru": "RPC ограничивает частоту — временно снизил опрос до {interval}с (вернусь к заданной, когда отпустит)",
        "en": "RPC is rate-limiting — temporarily slowed polling to {interval}s (will speed back up)",
        "zh": "RPC 触发频率限制——暂时将轮询降至 {interval} 秒（稍后自动恢复）"},
    "log_rpc_recovered": {
        "ru": "RPC отпустил — вернул опрос к {interval}с",
        "en": "RPC recovered — polling back at {interval}s",
        "zh": "RPC 已恢复——轮询回到 {interval} 秒"},
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
    "col_group": {"ru": "Группа", "en": "Group", "zh": "组"},
    "col_buyer": {"ru": "Кошелёк покупателя", "en": "Buyer wallet", "zh": "买家钱包"},
    "col_bought": {"ru": "Куплено", "en": "Bought", "zh": "买入量"},
    "row_risk": {"ru": "ОЦЕНКА ЗАПУСКА", "en": "LAUNCH SCORE", "zh": "上线评分"},
    "risk_level_high": {"ru": "⚠ ГРЯЗНЫЙ ЗАПУСК", "en": "⚠ DIRTY LAUNCH", "zh": "⚠ 上线不干净"},
    "risk_level_caution": {"ru": "⚠ ЕСТЬ К ЧЕМУ ПРИДРАТЬСЯ", "en": "⚠ WORTH A CLOSER LOOK", "zh": "⚠ 需要留意"},
    "risk_level_low": {"ru": "✓ ЗАПУСК ЧИСТЫЙ", "en": "✓ CLEAN LAUNCH", "zh": "✓ 上线干净"},
    "risk_level_none": {"ru": "нет данных", "en": "no data", "zh": "无数据"},
    "risk_score_hint": {"ru": "100% — ни одного признака манипуляции на запуске",
                         "en": "100% means no manipulation signals at launch",
                         "zh": "100% 表示上线时没有任何操纵迹象"},
    "risk_bundle_big": {"ru": "{pct:.1f}% предложения скупили связанные кошельки",
                         "en": "{pct:.1f}% of supply bought at launch by linked wallets",
                         "zh": "{pct:.1f}% 的供应量由关联钱包买入"},
    "risk_bundle_some": {"ru": "{pct:.1f}% предложения куплено связанными кошельками",
                          "en": "{pct:.1f}% of supply bought at launch by linked wallets",
                          "zh": "上线时 {pct:.1f}% 的供应量由关联钱包买入"},
    "risk_bundle_small": {"ru": "в окне запуска есть связанные кошельки",
                           "en": "linked wallets found in the launch window",
                           "zh": "上线窗口内发现关联钱包"},
    "risk_sniped_big": {"ru": "{pct:.0f}% предложения ушло в первую минуту",
                         "en": "{pct:.0f}% of supply taken in the first minute",
                         "zh": "第一分钟内已买走 {pct:.0f}% 的供应量"},
    "risk_sniped_some": {"ru": "{pct:.0f}% предложения ушло на запуске",
                          "en": "{pct:.0f}% of supply taken at launch",
                          "zh": "上线时买走了 {pct:.0f}% 的供应量"},
    "risk_top_wallet": {"ru": "один кошелёк взял {pct:.1f}% предложения",
                         "en": "one wallet took {pct:.1f}% of supply",
                         "zh": "单个钱包买走 {pct:.1f}% 的供应量"},
    "risk_overhang": {"ru": "бандл до сих пор держит {pct:.1f}% предложения",
                       "en": "the bundle still holds {pct:.1f}% of supply",
                       "zh": "捆绑钱包仍持有 {pct:.1f}% 的供应量"},
    "risk_concentration": {"ru": "10 крупнейших ранних кошельков держат {pct:.0f}%",
                            "en": "the 10 biggest early wallets hold {pct:.0f}%",
                            "zh": "最大的 10 个早期钱包持有 {pct:.0f}%"},
    "risk_clean": {"ru": "в окне запуска ничего подозрительного",
                    "en": "nothing suspicious in the launch window",
                    "zh": "上线窗口内未见异常"},
    "risk_disclaimer": {"ru": "оценка запуска, а не прогноз цены — не финансовый совет",
                         "en": "a launch score, not a price forecast — not financial advice",
                         "zh": "上线评分，非价格预测——非投资建议"},
    "col_now": {"ru": "Сейчас", "en": "Now", "zh": "现在"},
    "bundle_row_sold": {"ru": "вышел", "en": "sold", "zh": "已清仓"},
    "bundle_still_held": {"ru": "ЕЩЁ ДЕРЖАТ", "en": "STILL HELD", "zh": "仍持有"},
    "bundle_held_log": {"ru": "Ранние кошельки сейчас держат {pct:.2f}% предложения ({left} из {total} ещё в позиции)",
                         "en": "Early wallets now hold {pct:.2f}% of supply ({left} of {total} still in)",
                         "zh": "早期钱包当前持有供应量的 {pct:.2f}%（{total} 个中仍有 {left} 个持仓）"},

    "bundle_list_title": {"ru": "КТО КУПИЛ В ПЕРВЫЕ {w} СЕКУНД",
                           "en": "WHO BOUGHT IN THE FIRST {w} SECONDS",
                           "zh": "上线后 {w} 秒内的买家"},
    "bundle_list_hint": {"ru": "двойной клик — скопировать кошелёк",
                          "en": "double-click a row to copy the wallet",
                          "zh": "双击行可复制钱包地址"},
    "bundle_group_fmt": {"ru": "Г{n}", "en": "G{n}", "zh": "组{n}"},
    "bundle_group_alone": {"ru": "—", "en": "—", "zh": "—"},
    "bundle_funder_none": {"ru": "нет общего источника", "en": "no shared source", "zh": "无共用来源"},
    "bundle_funder_skipped": {"ru": "не проверялся", "en": "not checked", "zh": "未检测"},
    "bundle_stat_bundled": {"ru": "В БАНДЛЕ", "en": "BUNDLED", "zh": "捆绑占比"},
    "bundle_stat_early": {"ru": "РАННИЕ ПОКУПКИ", "en": "EARLY BUYS", "zh": "早期买入"},
    "bundle_stat_wallets": {"ru": "КОШЕЛЬКОВ", "en": "WALLETS", "zh": "钱包数"},
    "bundle_stat_groups": {"ru": "ГРУПП", "en": "GROUPS", "zh": "组数"},
    "bundle_stat_supply_hint": {"ru": "от предложения", "en": "of supply", "zh": "占供应量"},
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
    "bundle_table_idle": {"ru": "Вставьте адрес токена и нажмите Старт",
                           "en": "Paste a token address and press Start",
                           "zh": "粘贴代币地址并点击开始"},
    "bundle_table_checking": {"ru": "Идёт проверка ранних покупателей...",
                               "en": "Checking early buyers...",
                               "zh": "正在检查早期买家..."},
    "bundle_table_clean": {"ru": "Связанных кошельков не найдено — покупатели не связаны между собой",
                            "en": "No linked wallets found — buyers appear unrelated",
                            "zh": "未发现关联钱包——买家之间似乎互不相关"},
    "bundle_table_no_funder_check": {"ru": "Для этой сети связи кошельков не проверяются",
                                      "en": "Wallet links aren't checked on this network",
                                      "zh": "该网络不检查钱包关联"},
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
    "bundle_linking": {"ru": "Список готов. Проверяю, связаны ли кошельки между собой...",
                        "en": "List ready. Checking whether the wallets are linked...",
                        "zh": "列表已就绪，正在检查钱包之间是否关联..."},
    "bundle_scanning_launch": {"ru": "Ищу самые первые сделки после запуска токена...",
                                "en": "Scanning the earliest trades after launch...",
                                "zh": "正在扫描代币刚上线时的最早交易..."},
    "bundle_too_much_history": {
        "ru": "У токена слишком много истории — до момента запуска не добрались. Анализ бандлов надёжен для свежих токенов.",
        "en": "Too much history to reach the launch moment. Bundle analysis is reliable on freshly launched tokens.",
        "zh": "该代币历史记录过多，无法回溯到上线时刻。捆绑分析仅对新上线代币可靠。"},
    "bundle_no_history": {"ru": "Не удалось найти историю сделок для этого адреса.",
                           "en": "Could not find trade history for this address.",
                           "zh": "未能找到该地址的交易历史。"},
    "bundle_rpc_blocked": {
        "ru": "Публичный RPC ограничил запросы — данные не дочитались. Нажмите Старт ещё раз через несколько секунд.",
        "en": "The public RPC rate-limited us, so the data couldn't be read in full. Press Start again in a few seconds.",
        "zh": "公共 RPC 触发频率限制，数据未能完整读取。请几秒后再次点击开始。"},
    "bundle_no_supply": {
        "ru": "Не удалось прочитать общее предложение токена — проценты считать не из чего. Нажмите Старт ещё раз через несколько секунд.",
        "en": "Could not read the token's total supply, so no percentage can be computed. Press Start again in a few seconds.",
        "zh": "未能读取代币总供应量，无法计算占比。请几秒后再次点击开始。"},
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

    "tab_token": {"ru": "ТОКЕН", "en": "TOKEN", "zh": "代币"},
    "tab_new_pairs": {"ru": "НОВЫЕ", "en": "NEW PAIRS", "zh": "新交易对"},
    "tab_migrated": {"ru": "MIGRATED", "en": "MIGRATED", "zh": "已迁移"},
    "pairs_hint": {"ru": "{n} пулов создано недавно · двойной клик — разобрать токен",
                    "en": "{n} pools created recently · double-click to analyse",
                    "zh": "最近创建了 {n} 个资金池 · 双击进行分析"},
    "col_pair_token": {"ru": "Токен", "en": "Token", "zh": "代币"},
    "col_pair_age": {"ru": "Возраст", "en": "Age", "zh": "存续"},
    "pairs_loading": {"ru": "читаю новые пулы...", "en": "loading new pools...", "zh": "正在读取新资金池..."},
    "pairs_empty": {"ru": "новых пулов пока нет", "en": "no new pools yet", "zh": "暂无新资金池"},
    "pairs_failed": {"ru": "RPC не ответил, пробую снова", "en": "RPC did not answer, retrying",
                      "zh": "RPC 无响应，正在重试"},
    "migrated_todo": {
        "ru": "На Robinhood Chain отдельного шага миграции нет: пул Uniswap V4 создаётся сразу, и все такие пулы уже показаны во вкладке НОВЫЕ.\n\nНапишите, что здесь показывать — например токены, перешагнувшие определённый MCAP или объём, — и я заполню.",
        "en": "There is no separate migration step on Robinhood Chain: the Uniswap V4 pool is created straight away, and every such pool already appears under NEW PAIRS.\n\nTell me what this tab should list — tokens past a given MCAP or volume, for example — and I will fill it in.",
        "zh": "Robinhood Chain 上没有单独的迁移环节：Uniswap V4 资金池会直接创建，这些资金池都已显示在“新交易对”中。\n\n请告诉我这个标签页应该显示什么，例如超过某个市值或成交量的代币。"},
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

# Частота опроса блокчейна. Поля в интерфейсе намеренно нет: значение и так
# максимально быстрое, а при лимитах RPC цикл сам притормаживает (см. Pacer).
POLL_INTERVAL = 0.1

# Свой RPC-эндпоинт (снимает лимиты публичного). Из интерфейса убран, чтобы не
# мешал; при необходимости задаётся переменной окружения XBIT_RPC.
RPC_OVERRIDE = os.environ.get("XBIT_RPC") or None

# Ширина свечи на графике — секунда, как на биржевых терминалах.
CANDLE_SECONDS = 1

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


def find_early_signatures(rpc_url, address, window_seconds, max_pages=12, page_size=1000,
                           time_budget=45):
    """Пагинирует назад до самого начала истории адреса, затем возвращает подписи из
    первых window_seconds после самой первой сделки — то есть "окно запуска" токена.

    Страница берётся максимально возможная (1000): у активного токена тысячи подписей,
    и мелкими страницами дойти до начала истории не успеваем. hit_cap=True означает,
    что до реального начала не добрались — тогда результат считать нельзя."""
    all_sigs = []
    before = None
    started = time.time()
    reached_start = False

    for _ in range(max_pages):
        if time.time() - started > time_budget:
            break
        batch = _get_signatures_with_retry(rpc_url, address, page_size, before)
        if not batch:
            break
        all_sigs.extend(batch)
        before = batch[-1]["signature"]
        if len(batch) < page_size:
            reached_start = True
            break

    if not all_sigs:
        return [], None, False

    all_sigs.sort(key=lambda s: s.get("blockTime") or 0)
    launch_time = all_sigs[0].get("blockTime")
    early = [s for s in all_sigs
             if not s.get("err") and (s.get("blockTime") or 0) <= (launch_time or 0) + window_seconds]
    return early, launch_time, not reached_start


def find_wallet_funder(rpc_url, wallet, max_pages=3, page_size=1000):
    """Находит самую первую транзакцию кошелька и адрес, который его профинансировал
    (system transfer, где destination == wallet). None, если не удалось определить.

    Если до начала истории кошелька не добрались — возвращаем None, а не догадку:
    кошелёк с тысячами транзакций всё равно не похож на свежий кошелёк бандлера."""
    before = None
    oldest_batch = None
    reached_start = False
    for _ in range(max_pages):
        batch = _get_signatures_with_retry(rpc_url, wallet, page_size, before)
        if not batch:
            break
        oldest_batch = batch
        before = batch[-1]["signature"]
        if len(batch) < page_size:
            reached_start = True
            break

    if not oldest_batch or not reached_start:
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

    if hit_cap:
        emit("bundle_result", {"error": tr.t("bundle_too_much_history")})
        return

    per_wallet = {}
    for tx in _fetch_transactions_parallel(rpc_url, [s["signature"] for s in early_sigs], stop_event):
        trade = pumpfun_extract_trade(tx, curve_pda, assoc_curve, decimals)
        if trade and trade["is_buy"]:
            per_wallet[trade["wallet"]] = per_wallet.get(trade["wallet"], 0.0) + trade["token_amount"]

    _finish_bundle_check(per_wallet, total_supply, launch_time, hit_cap, window_seconds,
                          lambda w: find_wallet_funder(rpc_url, w), emit, tr, stop_event, max_wallets,
                          track={"kind": "solana", "rpc_url": rpc_url, "token": mint,
                                 "total_supply": total_supply})


def check_solana_dex_bundles(mint, pair_address, decimals, total_supply, rpc_url,
                              window_seconds, emit, tr, stop_event, max_wallets=25):
    emit("info", tr.t("bundle_scanning_launch"))
    early_sigs, launch_time, hit_cap = find_early_signatures(rpc_url, pair_address, window_seconds)
    if not early_sigs:
        emit("bundle_result", {"error": tr.t("bundle_no_history")})
        return

    if hit_cap:
        emit("bundle_result", {"error": tr.t("bundle_too_much_history")})
        return

    per_wallet = {}
    for tx in _fetch_transactions_parallel(rpc_url, [s["signature"] for s in early_sigs], stop_event):
        for owner, amount in solana_extract_buys(tx, mint, pool_owner_hint=pair_address):
            per_wallet[owner] = per_wallet.get(owner, 0.0) + amount

    _finish_bundle_check(per_wallet, total_supply, launch_time, hit_cap, window_seconds,
                          lambda w: find_wallet_funder(rpc_url, w), emit, tr, stop_event, max_wallets,
                          track={"kind": "solana", "rpc_url": rpc_url, "token": mint,
                                 "total_supply": total_supply})


def solana_get_wallet_token_balance(rpc_url, owner, mint):
    """Сколько токена лежит на кошельке прямо сейчас (сумма его token-аккаунтов)."""
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
        "params": [owner, {"mint": mint}, {"encoding": "jsonParsed"}],
    }
    result = http_post_json(rpc_url, payload).get("result") or {}
    total = 0.0
    for acc in result.get("value") or []:
        amount = acc["account"]["data"]["parsed"]["info"]["tokenAmount"]
        total += float(amount.get("uiAmountString") or 0)
    return total


def evm_get_token_balance(rpc_url, token_address, wallet):
    """balanceOf(address) — текущий баланс кошелька по токену."""
    data = "0x70a08231" + wallet.lower().replace("0x", "").rjust(64, "0")
    result = evm_rpc_call(rpc_url, "eth_call", [{"to": token_address, "data": data}, "latest"])
    return int(result, 16) if result and result != "0x" else 0


def track_bundle_holdings(track, wallets, emit, stop_event, interval=20.0):
    """Периодически перечитывает балансы ранних кошельков.

    Сам процент бандла — это факт из прошлого: столько было скуплено в окне
    запуска, и меняться он не может. А вот сколько из этого ещё лежит на тех же
    кошельках, меняется каждую минуту — именно это и нужно видеть живым."""
    kind = track.get("kind")
    rpc_url = track.get("rpc_url")
    token = track.get("token")
    total_supply = track.get("total_supply") or 0
    decimals = track.get("decimals") or 0
    if not wallets or not rpc_url or not token or not total_supply:
        return

    def balance_of(wallet):
        if kind == "evm":
            return evm_get_token_balance(rpc_url, token, wallet) / (10 ** decimals)
        return solana_get_wallet_token_balance(rpc_url, wallet, token)

    while not stop_event.is_set():
        held = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            future_map = {pool.submit(balance_of, w): w for w in wallets}
            for fut in concurrent.futures.as_completed(future_map):
                if stop_event.is_set():
                    return
                wallet = future_map[fut]
                try:
                    held[wallet] = fut.result()
                except Exception:
                    continue  # кошелёк не дочитался — прошлое значение не трогаем
        if held and not stop_event.is_set():
            emit("bundle_holdings", {
                "held_pct": {w: (a / total_supply * 100) for w, a in held.items()},
            })
        stop_event.wait(interval)


def assess_token_risk(data, held_by_wallet=None):
    """Считает оценку чистоты запуска по сигналам, видимым в цепочке.

    Оценка идёт от 100 вниз: каждый найденный признак манипуляции снимает
    баллы пропорционально своему размеру, и вместе со снятыми баллами
    возвращается текст — иначе число превратилось бы в чёрный ящик.

    Что оценка НЕ делает: не предсказывает цену и не советует покупать.
    Чистый запуск не мешает токену уйти в ноль по любой другой причине —
    например из-за самого контракта, который здесь не разбирается."""
    held_by_wallet = held_by_wallet or {}
    rows = data.get("wallet_rows") or []
    bundle_pct = data.get("bundle_pct") or 0.0
    early_pct = data.get("early_pct") or 0.0
    groups = len(data.get("bundle_clusters") or {})
    reasons = []   # (снятые баллы, ключ текста, параметры)

    # скоординированная закупка — самый прямой признак, за него и снимаем больше
    if bundle_pct >= 15:
        reasons.append((min(35, bundle_pct * 2.5), "risk_bundle_big",
                        {"pct": bundle_pct, "n": groups}))
    elif bundle_pct >= 5:
        reasons.append((bundle_pct * 2.0, "risk_bundle_some", {"pct": bundle_pct, "n": groups}))
    elif groups:
        reasons.append((6.0, "risk_bundle_small", {"pct": bundle_pct, "n": groups}))

    # часть предложения уходит на запуске всегда; штрафуем только перебор
    if early_pct >= 50:
        reasons.append((min(25, (early_pct - 25) * 0.5), "risk_sniped_big", {"pct": early_pct}))
    elif early_pct >= 25:
        reasons.append(((early_pct - 25) * 0.5, "risk_sniped_some", {"pct": early_pct}))

    top_pct = rows[0]["pct"] if rows else 0.0
    if top_pct >= 5:
        reasons.append((min(20, (top_pct - 5) * 2.0), "risk_top_wallet", {"pct": top_pct}))

    if held_by_wallet:
        # навес: сколько бандл держит прямо сейчас — это то, что может упасть на рынок
        bundle_held = sum(held_by_wallet.get(r["wallet"], 0.0) for r in rows if r.get("group"))
        if bundle_held >= 2:
            reasons.append((min(25, bundle_held * 2.5), "risk_overhang", {"pct": bundle_held}))

        top_now = sorted((held_by_wallet.get(r["wallet"], 0.0) for r in rows), reverse=True)[:10]
        concentration = sum(top_now)
        if concentration >= 20:
            reasons.append((min(20, (concentration - 20) * 0.5), "risk_concentration",
                            {"pct": concentration}))

    reasons = [(penalty, key, kwargs) for penalty, key, kwargs in reasons if penalty >= 1]
    reasons.sort(key=lambda item: item[0], reverse=True)   # сначала то, что весит больше
    score = max(0, round(100 - sum(penalty for penalty, _k, _kw in reasons)))

    if score >= 80:
        level = "low"
    elif score >= 50:
        level = "caution"
    else:
        level = "high"
    # запуск, где нашлись связанные кошельки, чистым назвать нельзя, каким бы
    # ни был балл: иначе ярлык противоречит причинам, перечисленным рядом
    if groups and level == "low":
        level = "caution"
    return {"score": score, "level": level, "reasons": reasons}


def _build_bundle_payload(per_wallet, total_supply, window_seconds, hit_cap, truncated,
                           funders, funder_unsupported, track):
    """Собирает то, что уходит в интерфейс. Вызывается дважды: сразу после разбора
    окна запуска (ещё без раздатчиков) и повторно, когда те дочитались."""
    clusters = {}
    for wallet, funder in (funders or {}).items():
        if funder:
            clusters.setdefault(funder, []).append(wallet)

    bundle_clusters = {}
    bundle_total = 0.0
    for funder, wallets in clusters.items():
        if len(wallets) < 2:
            continue
        cluster_amount = sum(per_wallet[w] for w in wallets)
        bundle_total += cluster_amount
        bundle_clusters[funder] = {
            "wallets": wallets,
            "amount": cluster_amount,
            "pct": (cluster_amount / total_supply * 100) if total_supply else 0.0,
        }

    group_of_funder = {}
    for idx, (funder, _c) in enumerate(
            sorted(bundle_clusters.items(), key=lambda kv: kv[1]["amount"], reverse=True), start=1):
        group_of_funder[funder] = idx

    wallet_rows = []
    for wallet, amount in sorted(per_wallet.items(), key=lambda kv: kv[1], reverse=True)[:200]:
        funder = (funders or {}).get(wallet)
        wallet_rows.append({
            "wallet": wallet,
            "amount": amount,
            "pct": (amount / total_supply * 100) if total_supply else 0.0,
            "funder": funder,
            "group": group_of_funder.get(funder),
            "checked": wallet in (funders or {}),
        })

    early_total = sum(per_wallet.values())
    return {
        "early_pct": (early_total / total_supply * 100) if total_supply else 0.0,
        "bundle_pct": (bundle_total / total_supply * 100) if total_supply else 0.0,
        "early_wallets": len(per_wallet),
        "bundle_clusters": bundle_clusters,
        "wallet_rows": wallet_rows,
        "track": track,
        "window_seconds": window_seconds,
        "hit_cap": hit_cap,
        "truncated": truncated,
        "funder_unsupported": funder_unsupported,
    }


def _finish_bundle_check(per_wallet, total_supply, launch_time, hit_cap, window_seconds,
                          funder_fn, emit, tr, stop_event, max_wallets, funder_unsupported=False,
                          track=None, hub_fn=None):
    if not per_wallet:
        emit("bundle_result", {"error": tr.t("bundle_no_early_buys")})
        return

    truncated = len(per_wallet) > max_wallets

    # Разбор окна занимает секунды, а поиск раздатчиков — почти минуту: обозреватель
    # отвечает на каждый кошелёк отдельно. Поэтому список покупателей показываем
    # сразу, а связи между ними дорисовываем, когда дочитаются.
    first = _build_bundle_payload(per_wallet, total_supply, window_seconds,
                                   hit_cap, truncated, None, funder_unsupported, track)
    first["funders_pending"] = not funder_unsupported
    emit("bundle_result", first)
    if funder_unsupported:
        return

    emit("info", tr.t("bundle_linking"))
    wallets = [w for w, _a in sorted(per_wallet.items(), key=lambda kv: kv[1], reverse=True)[:max_wallets]]

    def lookup_all(addresses):
        found = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            future_map = {pool.submit(funder_fn, a): a for a in addresses}
            for fut in concurrent.futures.as_completed(future_map):
                if stop_event.is_set():
                    return None
                try:
                    found[future_map[fut]] = fut.result()
                except Exception:
                    found[future_map[fut]] = None
        return found

    hop1 = lookup_all(wallets)
    if hop1 is None:
        return

    # Второй шаг. Типичная схема обхода: мастер-кошелёк пополняет по отдельному
    # промежуточному кошельку на каждого покупателя, и на первом шаге общего
    # источника просто не видно. Без хаб-фильтра второй шаг дал бы ложные связи,
    # поэтому он включается только там, где хабы можно распознать.
    hop2 = {}
    if hub_fn:
        hop2 = lookup_all({f for f in hop1.values() if f}) or {}
        if stop_event.is_set():
            return

    def shared(values):
        counts = {}
        for v in values:
            if v:
                counts[v.lower()] = counts.get(v.lower(), 0) + 1
        return {v for v, c in counts.items() if c >= 2}

    shared1 = shared(hop1.values())
    shared2 = shared(hop2.get(f) for f in hop1.values() if f)
    hubs = set()
    if hub_fn:
        for candidate in shared1 | shared2:
            if hub_fn(candidate):
                hubs.add(candidate)

    funders, hops = {}, {}
    for wallet, first in hop1.items():
        second = hop2.get(first) if first else None
        if first and first.lower() in shared1 and first.lower() not in hubs:
            funders[wallet], hops[wallet] = first, 1
        elif second and second.lower() in shared2 and second.lower() not in hubs:
            funders[wallet], hops[wallet] = second, 2
        else:
            funders[wallet], hops[wallet] = None, 0   # проверен, общего источника нет

    if stop_event.is_set():
        return
    final = _build_bundle_payload(per_wallet, total_supply, window_seconds,
                                   hit_cap, truncated, funders, False, track)
    for row in final["wallet_rows"]:
        row["hops"] = hops.get(row["wallet"], 0)
    emit("bundle_funders", final)


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
        data = None
        # обозреватель под нагрузкой регулярно отвечает 500; без повтора такой
        # кошелёк молча считался несвязанным, и размер бандла плавал от запуска
        # к запуску (12 → 8 → 7 кошельков на одном и том же токене)
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers=BLOCKSCOUT_HEADERS)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except Exception:
                time.sleep(0.5 * (2 ** attempt))
        if data is None:
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


def evm_is_funding_hub(chain_id, address, max_txs=5000):
    """Контракт или адрес с тысячами транзакций — биржа, мост, роутер. Через такие
    пополняются тысячи несвязанных людей, и группировать по ним нельзя: иначе
    каждый, кто вывел деньги с одной биржи, оказался бы "в одном бандле"."""
    base_url = BLOCKSCOUT_API_BASE.get(chain_id)
    if not base_url or not address:
        return False
    try:
        req = urllib.request.Request(f"{base_url}/api/v2/addresses/{address}", headers=BLOCKSCOUT_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            if json.loads(resp.read().decode("utf-8")).get("is_contract"):
                return True
        req = urllib.request.Request(f"{base_url}/api/v2/addresses/{address}/counters",
                                     headers=BLOCKSCOUT_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            count = int(json.loads(resp.read().decode("utf-8")).get("transactions_count") or 0)
        return count > max_txs
    except Exception:
        return False


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


def rpc_call_retry(fn, *args, tries=4, delay=0.6):
    """Повтор с нарастающей паузой для одиночных RPC-запросов.

    К моменту чтения supply мы уже успели прокачать через публичный RPC десятки
    тысяч логов, и он нередко отвечает 429 именно на этот запрос. Без повтора
    supply молча становился нулём, а вместе с ним обнулялись все проценты."""
    last_error = None
    for attempt in range(tries):
        try:
            return fn(*args)
        except Exception as e:
            last_error = e
            time.sleep(delay * (2 ** attempt))
    raise last_error


def evm_get_total_supply(rpc_url, token_address):
    """totalSupply() напрямую с контракта — не зависит от индексаторов."""
    result = evm_rpc_call(rpc_url, "eth_call", [{"to": token_address, "data": "0x18160ddd"}, "latest"])
    return int(result, 16) if result and result != "0x" else 0


# Uniswap V4 пишет Initialize ровно один раз на пул: topics = (id, currency0, currency1).
# Это единственный надёжный источник и момента запуска, и порядка токенов в паре.
UNISWAP_V4_INITIALIZE_TOPIC = "0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438"


def evm_find_pool_initialize(rpc_url, pool_manager, pool_id):
    """Возвращает блок создания пула и оба токена пары.

    Ищем окнами от свежих блоков к старым: у токена, который только запустился,
    Initialize лежит рядом с концом цепочки и находится с первой попытки, а
    сканирование всей истории занимает несколько секунд на каждый запуск."""
    try:
        latest = int(evm_rpc_call(rpc_url, "eth_blockNumber", []), 16)
    except Exception:
        latest = None

    ranges = []
    if latest:
        prev = latest
        for span in (100_000, 500_000, 2_000_000):
            floor = max(0, latest - span)
            ranges.append((floor, prev))
            prev = max(0, floor - 1)
            if floor == 0:
                break
    ranges.append((0, latest if latest else "latest"))

    logs = []
    for from_block, to_block in ranges:
        try:
            logs = evm_get_logs_retry(rpc_url, {
                "address": pool_manager,
                "topics": [UNISWAP_V4_INITIALIZE_TOPIC, pool_id],
                "fromBlock": hex(from_block),
                "toBlock": hex(to_block) if isinstance(to_block, int) else to_block,
            })
        except Exception:
            logs = []
        if logs:
            break
    if not logs:
        return None
    log = min(logs, key=lambda l: int(l["blockNumber"], 16))
    return {
        "block": int(log["blockNumber"], 16),
        "currency0": evm_topic_to_address(log["topics"][2]),
        "currency1": evm_topic_to_address(log["topics"][3]),
    }


# singleton PoolManager сети: все пулы Uniswap V4 живут в одном контракте
KNOWN_POOL_MANAGERS = {
    "robinhood": "0x8366a39cc670b4001a1121b8f6a443a643e40951",
}


def fetch_new_pairs(rpc_url, pool_manager, lookback_blocks=20000, limit=40, block_time=0.1):
    """Свежесозданные пулы: одно событие Initialize = один новый пул.

    Котируемые валюты определяем по самому списку — то, что встречается в разных
    пулах (нативная монета, USDG), это квоты, а новый токен — вторая сторона.
    Пары из двух квот пропускаем: нового токена в них нет."""
    latest = int(evm_rpc_call(rpc_url, "eth_blockNumber", []), 16)
    logs = evm_get_logs_retry(rpc_url, {
        "address": pool_manager, "topics": [UNISWAP_V4_INITIALIZE_TOPIC],
        "fromBlock": hex(max(0, latest - lookback_blocks)), "toBlock": hex(latest),
    })
    if not logs:
        return []

    seen = {}
    for lg in logs:
        for topic in (lg["topics"][2], lg["topics"][3]):
            address = evm_topic_to_address(topic).lower()
            seen[address] = seen.get(address, 0) + 1
    quotes = {address for address, count in seen.items() if count >= 3}
    quotes.add("0x0000000000000000000000000000000000000000")

    pairs = []
    for lg in sorted(logs, key=lambda l: int(l["blockNumber"], 16), reverse=True):
        c0 = evm_topic_to_address(lg["topics"][2])
        c1 = evm_topic_to_address(lg["topics"][3])
        candidates = [c for c in (c0, c1) if c.lower() not in quotes]
        if len(candidates) != 1:
            continue  # пара из двух квот либо два неизвестных токена — пропускаем
        block = int(lg["blockNumber"], 16)
        pairs.append({
            "token": candidates[0],
            "pool_id": lg["topics"][1],
            "block": block,
            "age_seconds": max(0, (latest - block) * block_time),
        })
        if len(pairs) >= limit:
            break
    return pairs


def fetch_all_pool_swaps(rpc_url, pool_manager, pool_id, lookback_blocks=1_500_000, stop_event=None):
    """Забирает ВСЕ свопы конкретного пула. Фильтр по poolId делает выборку маленькой,
    поэтому обычно хватает одного запроса на широкий диапазон; если RPC упрётся в лимит
    по числу логов — доберём частями."""
    try:
        latest = int(evm_rpc_call(rpc_url, "eth_blockNumber", []), 16)
    except Exception:
        return [], None, True
    floor = max(0, latest - lookback_blocks)
    topics = [UNISWAP_V4_SWAP_TOPIC, pool_id]

    logs = evm_get_logs_retry(rpc_url, {
        "address": pool_manager, "topics": topics,
        "fromBlock": hex(floor), "toBlock": hex(latest),
    })
    if logs:
        return sorted(logs, key=lambda l: int(l["blockNumber"], 16)), latest, False

    logs = []
    failures = 0
    chunks = 0
    cur = floor
    chunk = 100_000
    while cur <= latest:
        if stop_event is not None and stop_event.is_set():
            break
        to_block = min(cur + chunk, latest)
        chunks += 1
        try:
            batch = evm_rpc_call(rpc_url, "eth_getLogs", [{
                "address": pool_manager, "topics": topics,
                "fromBlock": hex(cur), "toBlock": hex(to_block),
            }])
            logs.extend(batch or [])
        except Exception:
            failures += 1
        cur = to_block + 1

    # пустой результат при сплошных ошибках — это не "сделок нет", а лимит RPC;
    # различаем, чтобы не показывать пользователю неверную причину
    rpc_blocked = not logs and failures > 0 and failures >= chunks / 2
    return sorted(logs, key=lambda l: int(l["blockNumber"], 16)), latest, rpc_blocked


def check_evm_bundles(ca, chain_id, info, rpc_url, window_seconds, emit, tr, stop_event, max_wallets=25):
    """Ищет скоординированные закупы в первые секунды жизни пула.

    Не опирается на Dexscreener: пул находится по логам самого токена, момент запуска —
    это первый Swap в пуле, а общее предложение берётся с контракта. Для токенов с GMGN,
    которых в Dexscreener ещё нет, это единственный рабочий путь."""
    emit("info", tr.t("bundle_scanning_launch"))

    pool_manager = pool_id = quote_address = None
    if info and info.get("pairAddress") and len(info["pairAddress"]) == 66:
        pool_id = info["pairAddress"]
        pool_manager = find_uniswap_v4_pool_manager(rpc_url, ca)
        quote_address = (info.get("quoteToken") or {}).get("address")
    if not pool_manager or not pool_id:
        discovered = discover_evm_pool_via_rpc(rpc_url, ca)
        if not discovered:
            emit("bundle_result", {"error": tr.t("log_v4_poolmanager_not_found")})
            return
        pool_manager = discovered["pool_manager"]
        pool_id = discovered["pool_id"]
        quote_address = quote_address or discovered.get("quote_token")

    # Момент запуска берём из Initialize, а не из "самого раннего найденного свопа":
    # широкий запрос логов RPC молча обрезает, и тогда за запуск принимался блок
    # на сотни тысяч блоков позже настоящего — вместе с ним уезжало и всё окно.
    init = evm_find_pool_initialize(rpc_url, pool_manager, pool_id)
    if not init:
        emit("bundle_result", {"error": tr.t("bundle_no_history")})
        return

    try:
        decimals = rpc_call_retry(evm_get_decimals, rpc_url, ca)
    except Exception:
        decimals = 18
    try:
        total_supply = rpc_call_retry(evm_get_total_supply, rpc_url, ca) / (10 ** decimals)
    except Exception:
        total_supply = 0
    if not total_supply:
        # без общего предложения все проценты — нули, показывать такое нельзя
        emit("bundle_result", {"error": tr.t("bundle_no_supply")})
        return

    first_block = init["block"]
    # порядок токенов тоже берём из Initialize: угадывание по адресам иногда
    # переворачивалось, и тогда все покупки читались как продажи
    is_token0 = init["currency0"].lower() == ca.lower()

    launch_ts = evm_block_timestamp(rpc_url, first_block) or 0
    later_ts = evm_block_timestamp(rpc_url, first_block + 5000)
    if launch_ts and later_ts and later_ts > launch_ts:
        block_time = (later_ts - launch_ts) / 5000
    else:
        block_time = 0.1  # разумная оценка для L2 — лучше, чем сузить окно в 10 раз
    window_blocks = max(1, int(window_seconds / max(block_time, 0.001)))
    last_block_in_window = first_block + window_blocks

    # запрашиваем ровно окно запуска: маленький диапазон читается целиком и быстро,
    # в отличие от прежнего прохода по всей истории пула
    try:
        swaps = evm_get_logs_retry(rpc_url, {
            "address": pool_manager,
            "topics": [UNISWAP_V4_SWAP_TOPIC, pool_id],
            "fromBlock": hex(first_block), "toBlock": hex(last_block_in_window),
        })
    except Exception:
        emit("bundle_result", {"error": tr.t("bundle_rpc_blocked")})
        return
    if not swaps:
        emit("bundle_result", {"error": tr.t("bundle_no_history")})
        return

    buys_by_tx = {}
    for lg in sorted(swaps, key=lambda l: int(l["blockNumber"], 16)):
        amount0 = evm_word_signed(lg["data"], 0)
        amount1 = evm_word_signed(lg["data"], 1)
        our_amount = amount0 if is_token0 else amount1
        if our_amount > 0:  # положительное = трейдер получает наш токен = покупка
            buys_by_tx[lg["transactionHash"]] = buys_by_tx.get(lg["transactionHash"], 0.0) +                 our_amount / (10 ** decimals)

    per_wallet = {}
    if buys_by_tx:
        tx_hashes = list(buys_by_tx.keys())
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            future_map = {
                pool.submit(evm_rpc_call, rpc_url, "eth_getTransactionByHash", [h]): h
                for h in tx_hashes
            }
            for fut in concurrent.futures.as_completed(future_map):
                if stop_event.is_set():
                    return
                tx_hash = future_map[fut]
                try:
                    tx = fut.result()
                except Exception:
                    continue
                wallet = tx.get("from") if tx else None
                if wallet:
                    per_wallet[wallet] = per_wallet.get(wallet, 0.0) + buys_by_tx[tx_hash]

    funder_unsupported = chain_id not in BLOCKSCOUT_API_BASE
    _finish_bundle_check(per_wallet, total_supply, launch_ts, False, window_seconds,
                          lambda w: evm_find_wallet_funder(chain_id, w), emit, tr, stop_event,
                          max_wallets, funder_unsupported=funder_unsupported,
                          track={"kind": "evm", "rpc_url": rpc_url, "token": ca,
                                 "decimals": decimals, "total_supply": total_supply},
                          hub_fn=lambda a: evm_is_funding_hub(chain_id, a))


def run_bundle_check(ca, emit, tr, stop_event, window_seconds=BUNDLE_WINDOW_SECONDS, rpc_override=None):
    ca = ca.strip()
    fmt = detect_chain_by_format(ca)
    if fmt == "evm":
        emit("info", tr.t("bundle_checking"))
        try:
            info = fetch_dexscreener_info(ca)
        except Exception:
            info = None

        if info and info.get("chainId"):
            chain_id = (info["chainId"] or "").lower()
            rpc_url = rpc_override or DEFAULT_EVM_RPCS.get(chain_id, DEFAULT_EVM_RPCS["ethereum"])
        elif rpc_override:
            chain_id, rpc_url = "custom", rpc_override
        else:
            # токена нет в Dexscreener (типичная ситуация для свежих с GMGN) —
            # определяем сеть по наличию контракта и работаем напрямую через RPC
            emit("info", tr.t("log_rpc_discovery"))
            chain_id, rpc_url = detect_evm_chain_for_token(ca)
            if not rpc_url:
                emit("bundle_result", {"error": tr.t("bundle_no_pair")})
                return

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
        total_supply = rpc_call_retry(solana_get_token_supply, rpc_url, ca)
    except Exception:
        total_supply = 0
    if not total_supply:
        emit("bundle_result", {"error": tr.t("bundle_no_supply")})
        return
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


def evm_block_timestamp(rpc_url, block_number, tries=3):
    """Время блока с ретраями — на нём считается окно запуска, ошибиться нельзя."""
    for attempt in range(tries):
        try:
            blk = evm_rpc_call(rpc_url, "eth_getBlockByNumber", [hex(block_number), False])
            if blk and blk.get("timestamp"):
                return int(blk["timestamp"], 16)
            return None
        except Exception:
            if attempt < tries - 1:
                time.sleep(0.4 * (attempt + 1))
    return None


def evm_get_logs_retry(rpc_url, params, tries=4):
    """eth_getLogs с ретраями: публичные RPC часто отвечают 429, а без повтора
    одна такая ошибка молча обнуляла поиск пула. Паузы растут (0.6/1.2/2.4с),
    чтобы пережить короткий эпизод троттлинга, а не сдаться на первой же ошибке."""
    for attempt in range(tries):
        try:
            return evm_rpc_call(rpc_url, "eth_getLogs", [params]) or []
        except Exception:
            if attempt < tries - 1:
                time.sleep(0.6 * (2 ** attempt))
    return []


def evm_decode_string(hex_result):
    """Декодирует ABI-строку из ответа eth_call (name()/symbol())."""
    if not hex_result or hex_result == "0x":
        return ""
    raw = bytes.fromhex(hex_result[2:])
    try:
        if len(raw) >= 64:  # динамическая строка: offset + length + данные
            length = int.from_bytes(raw[32:64], "big")
            if 0 < length <= len(raw) - 64:
                return raw[64:64 + length].decode("utf-8", "replace").strip("\x00")
        return raw.decode("utf-8", "replace").strip("\x00").strip()
    except Exception:
        return ""


def evm_get_token_identity(rpc_url, token_address):
    """name()/symbol() напрямую с контракта — нужно, когда Dexscreener токен ещё не знает."""
    name = symbol = ""
    try:
        name = evm_decode_string(
            evm_rpc_call(rpc_url, "eth_call", [{"to": token_address, "data": "0x06fdde03"}, "latest"]))
    except Exception:
        pass
    try:
        symbol = evm_decode_string(
            evm_rpc_call(rpc_url, "eth_call", [{"to": token_address, "data": "0x95d89b41"}, "latest"]))
    except Exception:
        pass
    return name, symbol


def detect_evm_chain_for_token(token_address, candidate_chains=("robinhood", "base", "ethereum", "bsc", "arbitrum")):
    """Когда Dexscreener молчит, сеть неизвестна — проверяем, на какой из известных
    сетей по этому адресу вообще есть контракт."""
    for chain_id in candidate_chains:
        rpc_url = DEFAULT_EVM_RPCS.get(chain_id)
        if not rpc_url:
            continue
        try:
            code = evm_rpc_call(rpc_url, "eth_getCode", [token_address, "latest"])
            if code and code != "0x":
                return chain_id, rpc_url
        except Exception:
            continue
    return None, None


def discover_evm_pool_via_rpc(rpc_url, token_address, lookback_blocks=100000,
                               chunk_blocks=5000, max_checked=25):
    """Находит пул Uniswap V4 для токена без Dexscreener: берём недавние переводы
    токена, смотрим их чеки и вытаскиваем из события Swap и адрес PoolManager,
    и сам poolId, а из переводов в той же транзакции — второй токен пары."""
    try:
        latest = int(evm_rpc_call(rpc_url, "eth_blockNumber", []), 16)
    except Exception:
        return None

    logs = []
    floor = max(0, latest - lookback_blocks)
    cur_to = latest
    while cur_to > floor and len(logs) < max_checked * 3:
        cur_from = max(floor, cur_to - chunk_blocks)
        logs.extend(evm_get_logs_retry(rpc_url, {
            "address": token_address, "topics": [TRANSFER_TOPIC],
            "fromBlock": hex(cur_from), "toBlock": hex(cur_to),
        }))
        cur_to = cur_from - 1

    seen_tx = set()
    checked = 0
    for lg in reversed(logs):
        tx_hash = lg.get("transactionHash")
        if not tx_hash or tx_hash in seen_tx or checked >= max_checked:
            continue
        seen_tx.add(tx_hash)
        checked += 1
        try:
            receipt = evm_rpc_call(rpc_url, "eth_getTransactionReceipt", [tx_hash])
        except Exception:
            continue

        receipt_logs = (receipt or {}).get("logs", [])
        swap = next((rl for rl in receipt_logs
                     if rl.get("topics") and rl["topics"][0].lower() == UNISWAP_V4_SWAP_TOPIC.lower()), None)
        if not swap:
            continue

        pool_manager = swap["address"]
        pool_id = swap["topics"][1]
        pm_topic = evm_pad_address_topic(pool_manager).lower()

        quote_token = None
        for rl in receipt_logs:
            if (rl.get("address") or "").lower() == token_address.lower():
                continue
            topics = rl.get("topics") or []
            if len(topics) < 3 or topics[0].lower() != TRANSFER_TOPIC.lower():
                continue
            if topics[1].lower() == pm_topic or topics[2].lower() == pm_topic:
                quote_token = rl["address"]
                break

        return {"pool_manager": pool_manager, "pool_id": pool_id, "quote_token": quote_token}
    return None


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


class Pacer:
    """Держит заданный интервал опроса, но при ошибках RPC (обычно 429) временно
    замедляется и потом сам возвращается к заданной частоте. Сообщение о замедлении
    пишем один раз на эпизод, а не на каждую ошибку — иначе лог превращается в спам."""

    def __init__(self, interval, emit, tr, max_delay=8.0):
        self.base = interval
        self.delay = interval
        self.max_delay = max(max_delay, interval)
        self.emit = emit
        self.tr = tr
        self._throttled = False
        self._ok_streak = 0

    def on_error(self, err):
        self.delay = min(max(self.delay * 2, 0.5), self.max_delay)
        self._ok_streak = 0
        if not self._throttled:
            self._throttled = True
            # это не поломка, а нормальная реакция на лимит — пишем как info,
            # чтобы не выглядело ошибкой в логе
            self.emit("info", self.tr.t("log_rpc_throttled", interval=round(self.delay, 1)))

    def on_success(self):
        if self.delay <= self.base:
            return
        self._ok_streak += 1
        if self._ok_streak >= 5:  # уверенно отпустило — возвращаем прежний темп
            self.delay = max(self.base, self.delay / 2)
            self._ok_streak = 0
            if self.delay <= self.base and self._throttled:
                self._throttled = False
                self.emit("info", self.tr.t("log_rpc_recovered", interval=self.base))


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

    # адаптивный темп: держим заданный интервал, но при лимитах RPC временно
    # замедляемся и постепенно возвращаемся обратно — вместо спама ошибками
    pace = Pacer(interval, emit, tr)

    while not stop_event.is_set():
        try:
            latest = int(evm_rpc_call(rpc_url, "eth_blockNumber", []), 16)
        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
            pace.on_error(e)
            stop_event.wait(pace.delay)
            continue

        if latest > last_block:
            try:
                logs = evm_rpc_call(rpc_url, "eth_getLogs", [{
                    "address": pool_manager, "topics": [UNISWAP_V4_SWAP_TOPIC, pool_id],
                    "fromBlock": hex(last_block + 1), "toBlock": hex(latest),
                }])
            except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
                pace.on_error(e)
                stop_event.wait(pace.delay)
                continue

            pace.on_success()

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
        stop_event.wait(pace.delay)


# ---------------------------------------------------------------------------
# Оркестратор
# ---------------------------------------------------------------------------

def watch_evm_without_dexscreener(ca, interval, emit, stop_event, tr, rpc_override=None):
    """Путь для токенов, которых Dexscreener ещё не знает: сеть определяем по наличию
    контракта, пул — по логам Swap в недавних транзакциях токена."""
    emit("info", tr.t("log_rpc_discovery"))

    if rpc_override:
        chain_id, rpc_url = "custom", rpc_override
    else:
        chain_id, rpc_url = detect_evm_chain_for_token(ca)
        if not rpc_url:
            emit("error", tr.t("log_no_pair"))
            return

    pool = discover_evm_pool_via_rpc(rpc_url, ca)
    if not pool or not pool.get("quote_token"):
        emit("error", tr.t("log_no_pair"))
        return

    name, symbol = evm_get_token_identity(rpc_url, ca)
    emit("meta", {
        "name": name or ca[:10], "symbol": symbol,
        "network": chain_display_name(chain_id), "dex": "Uniswap V4",
        "price": "", "liquidity": "",
        # без Dexscreener нет якоря капитализации — показываем цену как есть,
        # а не выдуманный MCAP
        "mcap_anchor": None, "mcap_unit": "", "mcap_unit_is_prefix": True,
        "price_native_anchor": None,
    })
    emit("info", tr.t("log_v4_detected", chain=chain_id))

    watch_evm_v4(ca, chain_id, pool["pool_manager"], pool["pool_id"],
                 pool["quote_token"], "", rpc_url, interval, emit, stop_event, tr)


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
        # Dexscreener индексирует новые токены с задержкой — у совсем свежих его данных
        # ещё нет. Пробуем найти пул сами, напрямую через RPC.
        if fmt == "evm":
            watch_evm_without_dexscreener(ca, interval, emit, stop_event, tr, rpc_override)
            return
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
    "iVBORw0KGgoAAAANSUhEUgAAACwAAAAsCAIAAACR5s1WAAAMk0lEQVR4nJ1YaXRV13U+0x3ePEl6AklGYsbIFpg4JoAH5kA8"
    "htiGxhCS2klwiRviBIzjmMaAQxvANbhrGTsmaVfaYCe4rdvGzlCv2PXcGJtBTJIQmiV4kt50h3fPsLuuYPmXn1xx1l13vXV/"
    "vPOdb+9v7+9sHAzHUZklgCukgBCMMcIYEYoZI6ZBImGWSuoVlayygoRDwLkYHOYDAzyTkbkcOCXgHKREAAAKAWAAggjDWrmN"
    "GBplEQyIYEwxJYhSTCnWNRoKsWTSqK0zJ07UJ1xlJhKy5Dnd3W5bK8IYSyUBKYyRlJcfpAD8T6PsMzoISoj/RhrzOdA1Ypg0"
    "FtXTaWPCVZG5N8i+/lMPb66YN7fmwW8NYwSehzwPEMLMVpwrLrEQWCklOMIIwRWBwISA/sn2BjZNGgyyeIylksEZM7yjx/pP"
    "n775N4dPfvBm19796XX38cGMLOQRgNQ0VHKwj4lLT2CMMZdIXgEIQIgybOjUNKkZIIEADQdJMMQScT2R1JNJ5/jJYnfv+Ouv"
    "b+s+e+H02bpoVIslVKoCK0QMgziOclxl24g4ihOkPCSkz8ennrZsYgJAPIxjYRoIskiYRMI0EqGRCIvG9HQ6UF+vJRJ2S9uZ"
    "l39dMX1m7fLlgJHTfq7U18eHhmQ+LwsFaduyUJS2pWwb8jaxXD+7x8gE0GCAJhI0FKLxmJZMsViMxmJaJMriMWwYKJlIrf5K"
    "fP8z6a+tN+d+zvnzEb2yAjPGYjE+PCzyOZHNEkMneV0wTXoCFd1yTJQBgTECRIJBlkqyWExLVeqVFVoiTsNhI53W01UoEpG5"
    "nPXGm2AabmuLearOnDIJHFvm8m5nF4tFRS7PQxluBriWwTpDlqMghzBBAGNgAgBoKKRVVuqJlFFdzVIJI50OTZvS/9tXz/1o"
    "m15RUeroRM0nEWO5D4+g3X+fmD9PWbY5blz9tkd5Lu+2n2emSXQDM8p1TWWGVXl5jBYOFo2Z6XF6RQWrSIavaRz605vHd+5a"
    "OKvp++vuL2BBDZ0Gg0gqTDAX4lCxt0gwLtpnNm4KpCvqHv6e09WFGPOrC6Oiux8U4LGDUCweN2trWCwabmrq+6/Xpre3bly9"
    "xl1xozWpiYyoh6PLUZYI1SHlIgJoCCVjPf/T3LNv3/hNf01M04+sxkptHQjUGJnAGAC0eNxPherq3Gt/yLR+vPyhR5qo9vhT"
    "e48yrvv1HEaQXD5eCFP/l5KhGVMn/92W9u37+54/WLVqlV6dxhpzI1E/G/xUgzGGIxbVJ0wINc5s3fPULQvmcE9sfGRzc0en"
    "pulFqTCjl+vgyHtICkQIAqS9e6LBds3lKy58e0PNgxu02hq3pYWGQgBjDwdIpaVS1kdHO//lV7kTzYvuvKv31d82nz4VXfc1"
    "STHWdDE4iDjHI5xhw6CpJJRKsmjBwEDrnoNVP52GQ8FTu/dGK6vSyxZriThSZcNBPj0ayEdhVlZ2/cd/rixYSydOfqnY/3FC"
    "I7ohkZqwYU3Dpq9rVUmZzYPjymzOqKue+N37x6+/C4RQjqNXJCQhOkLfa2x0D70oFLB4DFTZJvbpIC4tMA0tGHTuWmRfN72f"
    "2z2qpCQCw2CVCT2UwoGAzz/Bfo8Jh/RgSq9KIk0byQzlP7qeX3crnVBDgkFsBvyYjbliIgBd1wg7kb+YcwoxksQj4QfLGn7r"
    "QxoKy4tDwAVoDKT0uvuGjrxfylxEbglhAggRwBLB28O9judRw/Qr7BW2csYwyFxn0R7mUTxyDkqgYPW98BJCmGosMn2i2zNg"
    "1Neqot2x51lCKTH1y3LBoKQaardE0VEaA00bpZd/ejgAI4yIl8+nd+50Trdk//UVvapCWjYSigRMFg5p0TDWNJqIV9+xIjrr"
    "aqVAi0ZoJIQNA1OKvBIiRDhO56atVdv/Bk9uACE+EfOYmMAIgEyqDz+6xT3f1vWnE5N2bJpwvrvj0G+06VN9/4LQ8NHjw5TA"
    "SNH098YEew4ZGoz+YAuOJ2jJi+zcxlYs9a3daISPGg4gRLqWargq+NzzzhPbO184XPPYlnGrb5XU/1NAPl2XEwUQIN9L9pzo"
    "42ZEq60t7NkTeGYvvfNWkS+CRhAlVwoCIcWYLGTlpAn0kS2F3Xvb7n0lVFupDBMpgYT4JNt9F4kQNk2rKHjfRYYR/s4D6o4v"
    "CcsCpRQlUEYXnw0C+TjA95jSxTOb2I5Hvbc/4LGEt+VRfXqj9vnrwbJ9ifrlGwij+QMHZMf58DN7oelaumAxRpyEKWRzvlzL"
    "G8zP8pgIsJA0lkQHns2++GtWW6s0TXGBBgf5yRNaPks8frkdYOxXccsihsH/+Do+cbK4azdSMphMRnftINHRyuVnMSEV04Jy"
    "3/6hx7Zt+Pa3/vftdydfPX3FipXW2nUGJa94F7uxR8GnWrqOXzM23tvfPuz1DxWeO7B188P19ZO2/uUD/f0X47/8BRpVouVB"
    "YISE0qg2+Mf//uZ9a2c8+ZN/W7/6viVLjXtXH35qh3jno7Nh44JAESowLwU3bKhZcIOGePZEFypw9rtXb1n15WMNU6am4dja"
    "h2VmkFA6diZgBAYoghCj2sUF17zsZfvOdmiMvvi3T75ytlW75rqkl7vZ7H6nNFUQbfDxPYldD0XmzFa5PBQ54vxng22Z2sBQ"
    "ZR1OpSjAyC1orCAuLSkJAl2oM2AzHWNgxNTdd98LNM2Orv36bOvIzvSr3+hb3GXUeYdfgqFBQg0/TwlBCrqjekKLu5kW4XhU"
    "wZXkBB55YSmo4iwa6n7iH/R//h20nuFcTNmx/Y1tPxy+feVbIWO+4JJ8ILkMLF/JmpoALN/KIgSUnF2/WSZiPGdDLuvLk3/i"
    "wv7fIC4tzDlVEkpecsk8esuyTGsHtZ2qxqapj31T6+xTmu7XK1AEJJl9XXhcjULFEVH7sUzfvWL15Ot/efR42z/+HHPPLyrl"
    "V/lChhGUXOp54JSSN30+8pU7SCL1+wQ+9OPNtFTyFq0ILFsk58wNf2mp+7kbzcrkmY3fd0+d0ytTxDAQRtW3LbnpttsTX1wG"
    "gQCxXVzyLjuwsfYOcEq+9AHxQlFdzBjBwO83/eg7Gx/K1Mw4wvMEU5MKZNtBypGi47965/kn9g+39SpCxMAFbtkO9/0OUkpZ"
    "lnSckWONWaJY2ZbK55DgLBSEeBRhRGfO6f/G3aWgnkA5hqgRxoDACOqAULZ+hjt/SWCWjRDK/+x5LRQ8rMlcyNAI5fmstIrl"
    "HE1ZEDACQhSKfGCABI3mbU8bP/93cfw4qm94edW65APr2azZynb8fyX4Ugdzhm19/nxr377Q7XfQdPq9e/7qw3FVfCAHQ0Ne"
    "Li+yWexPO8bGBPgg8jkxcKEwcOH+2+48d23TW18uwfPPFV973Tvfh8Nh/5ZtGCA4EtKfGiCJhXSbm70jR8Tg0NYfbn1Z4S6r"
    "qJ474Pb0inx+RDhjygnwvQHP5wstrTULb2pZtGhgRqN8fNtV96waTCX4+Dpz3heU4Pmnn6655+7IjQvOfXcTW7hYb2wMEzy8"
    "Z48YGHi3caabqpDbflx5803SK3mDg/645wpyQmRzxY6OSEP9+wd/UTx6rG7BFyqWLc2+937mnbfcni6KkMzmYjffmFzyxZ7a"
    "PYOvv07OnNYFB8ua8tjWN578CfQPVM2cwSqS7oUBWShcKiFjB1Es8szFvOBxXYvNagrPapLDQ4Xevk1r1vTNm/2H853ifJfs"
    "6lTd7aVcfsvav7h2zg3bj3189oWDWjI5Yc511rl2mq5yenv8iYXtjOIoyoUD/CGYZXkXMtJyjKpKra7G7ekjCBO31L6wKXjL"
    "XfHeluLBQ7ynr3S+A5dKHSvnillLYWIN/dWLVlurVj2OJROljg6ezcmiJW273FzgMyY1KBWliRgNhmg4yAJBY3z18PHmwp8/"
    "YlMbwvGo8JTd0l7/1TXRpsaTu34qGPhzi4IjznVoqWT02kbleaJQED4CC3JFnLfLqXQUEEiFDRwO+AMowzQS8Xxn14YHNyy+"
    "aeE/OZ1vnu2VLrEOPJucNrnQ1/+DB+4/PbnmtJcZaM2WFMvv3m3GwtgwRDanSq4qecguUVeMfWaFkNQpGCPTO0NnoZDd0z9l"
    "2tRx42vakZuxPVVS3snm2Ixp+Za2qxsaitWpvCq5RSkcV7S2apEQBpCOozwOXBAhaPnuMRoIQQEoGZlyMKwxommO44ACTdM1"
    "/yPBZoBFwkiIwnCWCkGk8ocQSvq3JkIU97cHKUEIohCDsuoYFQSWauSmeXmcyyjVdaJpiFKgxPeV/ihF+fckQhGAkgKE9B/O"
    "fQKkREqBUgCKKsTKK/H/AF+dZ99xoH51AAAAAElFTkSuQmCC"
)


# ---- палитра "кислотный терминал" -----------------------------------------
# Оформление держится на одном акценте — ядовитом лайме. Зелёный и красный
# оставлены исключительно за смыслом "рост / падение": это цвет данных, а не
# интерфейса, поэтому в хроме они не встречаются.
BG = "#08090a"
PANEL = "#101214"
PANEL2 = "#16191c"
BORDER = "#1e2226"
BORDER_HI = "#2f363b"       # рамка карточки/поля под фокусом
TEXT = "#e8ece8"
MUTED = "#6f7a72"
FAINT = "#3d453f"           # самые тихие подписи, вроде дисклеймера
ACCENT = "#ccff00"
ACCENT_HOVER = "#e2ff4d"
ACCENT_DIM = "#3d4a00"      # акцент в неактивном состоянии
ON_ACCENT = "#08090a"       # текст поверх акцентной заливки: лайм слишком яркий для белого
GREEN = "#00ff9d"
GREEN_DIM = "#00593a"
RED = "#ff2d55"
RED_DIM = "#5c1023"
GOLD = "#ffe100"            # предупреждение: ровно между лаймом и красным
ROW_BUY = "#08201a"
ROW_BUY_ALT = "#0b2a21"
ROW_SELL = "#210911"
ROW_SELL_ALT = "#2b0d17"
ROW_SELECTED = "#2a3609"    # выделение строки — приглушённый лайм
# (фон, текст) на группу: одинаковый красный не давал отличить Г1 от Г2
GROUP_TINTS = (("#2c0c17", "#ff2d55"), ("#2b2200", "#ffe100"),
               ("#231033", "#c77dff"), ("#062b2a", "#26e0d4"))
EXITED = "#4b544d"

# терминал — значит моноширинный шрифт везде, включая заголовки
MONO = "Consolas"


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
        root.geometry("1240x900")
        root.configure(bg=BG)
        root.minsize(1040, 840)

        self._build_style()
        self._build_ui()

        self.log_queue = queue.Queue()
        self.stop_event = None
        self._bundle_stop_event = None
        self._holdings_stop = None
        self.worker = None
        self.meta_widgets = {}

        # живая статистика сессии
        self.buy_count = 0
        self.sell_count = 0
        self.buy_volume = 0.0
        self.sell_volume = 0.0
        self.quote_symbol = ""
        self.candles = []
        self.candle_seconds = CANDLE_SECONDS
        self.max_candles = 90
        self.mcap_anchor = None
        self.mcap_unit = ""
        self.mcap_unit_is_prefix = True
        self.price_native_anchor = None
        self._live_on = False
        self._live_blink_state = True

        self.root.after(120, self.drain_queue)
        self.root.after(500, self._blink_live_dot)
        self.root.after(1000, self._tick_clock)
        self.root.after(1000, self._tick_candles)
        self.root.after(15000, self._tick_new_pairs)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.retranslate()
        self.select_left_tab("tab_new_pairs")
        self._show_ca_placeholder()
        self.clear_bundle_table("bundle_table_idle")  # пустая таблица сразу объясняет себя

    # -- style ---------------------------------------------------------
    def _build_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)

        style.configure("TLabel", background=BG, foreground=TEXT, font=(MONO, 10))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(MONO, 9))
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=(MONO, 9))
        style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED, font=(MONO, 8))
        style.configure("PanelValue.TLabel", background=PANEL, foreground=TEXT, font=(MONO, 11, "bold"))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=(MONO, 16, "bold"))
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=(MONO, 9))
        style.configure("Status.TLabel", background=BG, foreground=MUTED, font=(MONO, 9))

        style.configure("TEntry", fieldbackground=PANEL2, foreground=TEXT, insertcolor=TEXT,
                         bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=6)
        style.map("TEntry", fieldbackground=[("readonly", PANEL2)])

        # на лайме читается только чёрный текст — белый на такой яркости слепнет
        style.configure("Accent.TButton", background=ACCENT, foreground=ON_ACCENT,
                         font=(MONO, 10, "bold"), padding=(16, 9), borderwidth=0,
                         focuscolor=ACCENT)
        style.map("Accent.TButton", background=[("active", ACCENT_HOVER), ("disabled", ACCENT_DIM)],
                  foreground=[("disabled", MUTED)])

        style.configure("Stop.TButton", background=PANEL2, foreground=RED,
                         font=(MONO, 10, "bold"), padding=(16, 9), borderwidth=2,
                         bordercolor=RED_DIM, lightcolor=PANEL2, darkcolor=PANEL2, focuscolor=PANEL2)
        style.map("Stop.TButton", background=[("active", RED_DIM), ("disabled", PANEL2)],
                  foreground=[("disabled", FAINT)],
                  bordercolor=[("disabled", BORDER)])

        style.configure("Ghost.TButton", background=BG, foreground=MUTED,
                         font=(MONO, 9), padding=(12, 7), borderwidth=2,
                         bordercolor=BORDER, lightcolor=BG, darkcolor=BG, focuscolor=BG)
        style.map("Ghost.TButton", background=[("active", PANEL)], foreground=[("active", ACCENT)],
                  bordercolor=[("active", BORDER_HI)])

        style.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2, foreground=TEXT,
                         arrowcolor=TEXT, bordercolor=BORDER, padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL2)])

        # borderwidth+relief+*color гасят светлую рамку, которую clam рисует вокруг
        # таблицы — на тёмной теме она выглядела как чужеродный белый прямоугольник
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                         rowheight=25, font=(MONO, 10), borderwidth=0, relief="flat",
                         bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL)
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure("Treeview.Heading", background=BG, foreground=ACCENT,
                         font=(MONO, 8, "bold"), borderwidth=0, relief="flat", padding=(8, 6))
        style.map("Treeview.Heading", background=[("active", BG)], foreground=[("active", ACCENT_HOVER)])
        style.map("Treeview", background=[("selected", ROW_SELECTED)], foreground=[("selected", TEXT)])

        for sb in ("Vertical.TScrollbar", "TScrollbar"):
            style.configure(sb, background=BORDER, troughcolor=BG, bordercolor=BG,
                             arrowcolor=MUTED, lightcolor=BORDER, darkcolor=BORDER,
                             borderwidth=0, relief="flat", arrowsize=10)
            style.map(sb, background=[("active", ACCENT_DIM)])

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
        self.subtitle_lbl = tk.Label(brand_box, bg=BG, fg=MUTED, font=(MONO, 9), anchor="w")
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

        # сегментированный переключатель вместо выпадающего списка: три плитки,
        # активная подсвечена акцентом — выпадашка выбивалась из тёмного интерфейса
        lang_box = tk.Frame(header, bg=BG)
        lang_box.pack(side="right", padx=(0, 26))
        self.lang_lbl = tk.Label(lang_box, bg=BG, fg=MUTED, font=(MONO, 8, "bold"))
        self.lang_lbl.pack(anchor="e")

        seg = tk.Frame(lang_box, bg=BORDER)
        seg.pack(anchor="e", pady=(3, 0))
        seg_inner = tk.Frame(seg, bg=PANEL2)
        seg_inner.pack(padx=1, pady=1)

        self.lang_buttons = {}
        for code in LANGS:
            btn = tk.Label(seg_inner, text=LANG_NAMES[code], bg=PANEL2, fg=MUTED,
                            font=(MONO, 9, "bold"), padx=10, pady=3, cursor="hand2")
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda e, c=code: self.set_language(c))
            self.lang_buttons[code] = btn
        self._refresh_lang_buttons()

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", padx=18)

        # ---- input row ----
        input_row = ttk.Frame(self.root, padding=(18, 10, 18, 10))
        input_row.pack(fill="x")

        # поле ввода собрано вручную: ttk.Entry в теме clam рисует светлую рамку и
        # выглядит чужеродно на тёмном фоне. Здесь — рамка в 1px, метка CA слева
        # и подсказка прямо внутри поля, которая гаснет при вводе.
        self.ca_border = tk.Frame(input_row, bg=BORDER)
        self.ca_border.pack(side="left", fill="x", expand=True)
        ca_inner = tk.Frame(self.ca_border, bg=PANEL2)
        ca_inner.pack(fill="both", expand=True, padx=2, pady=2)

        tk.Label(ca_inner, text="CA", bg=PANEL2, fg=ACCENT,
                 font=("Consolas", 10, "bold"), padx=13).pack(side="left")
        tk.Frame(ca_inner, bg=BORDER, width=1).pack(side="left", fill="y", pady=7)

        self.ca_entry = tk.Entry(ca_inner, bg=PANEL2, fg=TEXT, insertbackground=ACCENT,
                                  font=("Consolas", 11), relief="flat", bd=0,
                                  highlightthickness=0, disabledbackground=PANEL2,
                                  disabledforeground=MUTED)
        self.ca_entry.pack(side="left", fill="both", expand=True, padx=12, pady=10)
        self.ca_entry.bind("<Return>", lambda e: self.start())
        self.ca_entry.bind("<FocusIn>", self._on_ca_focus_in)
        self.ca_entry.bind("<FocusOut>", self._on_ca_focus_out)
        self._ca_placeholder_on = False

        btn_col = ttk.Frame(input_row)
        btn_col.pack(side="left", padx=(12, 0), fill="y")
        self.start_btn = ttk.Button(btn_col, style="Accent.TButton", command=self.start)
        self.start_btn.pack(side="left", fill="y")
        self.stop_btn = ttk.Button(btn_col, style="Stop.TButton", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6, fill="y")
        self.clear_btn = ttk.Button(btn_col, style="Ghost.TButton", command=self.clear)
        self.clear_btn.pack(side="left", fill="y")

        # ---- тело: три колонки ----
        body = ttk.Frame(self.root, padding=(18, 0, 18, 8))
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._build_token_card(body)
        self._build_bundle_card(body)   # центр — главное: анализ бандлов

        # ---- второстепенная полоса: график + лента сделок ----
        self._build_bottom_strip()

        # ---- панель логов ----
        log_frame = ttk.Frame(self.root, padding=(18, 0, 18, 6))
        log_frame.pack(fill="x")
        self.log_text = tk.Text(log_frame, height=3, bg=PANEL, fg=MUTED, insertbackground=TEXT,
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

    # -- поле ввода CA ---------------------------------------------------
    def _show_ca_placeholder(self):
        if str(self.ca_entry.cget("state")) == "disabled":
            return
        if not self.ca_entry.get():
            self._ca_placeholder_on = True
            self.ca_entry.insert(0, self.tr.t("ca_placeholder"))
            self.ca_entry.configure(fg=MUTED)

    def _hide_ca_placeholder(self):
        if self._ca_placeholder_on:
            self._ca_placeholder_on = False
            self.ca_entry.delete(0, "end")
            self.ca_entry.configure(fg=TEXT)

    def _on_ca_focus_in(self, _event=None):
        self._hide_ca_placeholder()
        self.ca_border.configure(bg=ACCENT)  # рамка подсвечивается акцентом в фокусе

    def _on_ca_focus_out(self, _event=None):
        self.ca_border.configure(bg=BORDER)
        self._show_ca_placeholder()

    def ca_text(self):
        """Текст поля без подсказки — иначе Старт принял бы её за адрес."""
        return "" if self._ca_placeholder_on else self.ca_entry.get().strip()

    def _header_stat(self, parent, color, last=False):
        box = tk.Frame(parent, bg=BG)
        box.pack(side="left", padx=(0, 0) if last else (0, 22))
        cap = tk.Label(box, bg=BG, fg=MUTED, font=(MONO, 8, "bold"))
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
        inner.pack(fill="both", expand=True, padx=2, pady=2)
        return inner

    def _build_token_card(self, parent):
        card = self._card(parent, 0, minwidth=268)

        # вкладки вместо второй карточки: список новых пар занимает то же место,
        # что и данные токена, и не прибавляет окну высоты
        tabs = tk.Frame(card, bg=PANEL)
        tabs.pack(fill="x", padx=1, pady=(1, 0))
        self.left_tabs = {}
        for key in ("tab_token", "tab_new_pairs", "tab_migrated"):
            btn = tk.Label(tabs, bg=PANEL, fg=MUTED, font=(MONO, 8, "bold"),
                            padx=8, pady=6, cursor="hand2")
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda e, k=key: self.select_left_tab(k))
            self.left_tabs[key] = btn
        tk.Frame(card, bg=BORDER, height=1).pack(fill="x")

        self.left_panes = {}
        holder = tk.Frame(card, bg=PANEL)
        holder.pack(fill="both", expand=True)
        self._left_holder = holder

        pad = tk.Frame(holder, bg=PANEL, padx=14, pady=12)
        self.left_panes["tab_token"] = pad
        self._build_new_pairs_pane(holder)
        self._active_left_tab = None

        self.token_card_title = tk.Label(pad, bg=PANEL, fg=ACCENT, font=(MONO, 8, "bold"))
        self.token_card_title.pack(anchor="w")

        id_row = tk.Frame(pad, bg=PANEL)
        id_row.pack(fill="x", pady=(10, 12))
        self.token_icon = tk.Label(id_row, text="?", width=3, bg=ACCENT, fg=ON_ACCENT,
                                    font=(MONO, 12, "bold"))
        self.token_icon.pack(side="left")
        name_box = tk.Frame(id_row, bg=PANEL)
        name_box.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self.token_name_lbl = tk.Label(name_box, text="—", bg=PANEL, fg=TEXT,
                                        font=(MONO, 12, "bold"), anchor="w")
        self.token_name_lbl.pack(fill="x")
        self.token_symbol_lbl = tk.Label(name_box, text="", bg=PANEL, fg=MUTED,
                                          font=(MONO, 9), anchor="w")
        self.token_symbol_lbl.pack(fill="x")

        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=(0, 10))

        self.token_rows = {}
        for key, field in [("row_network", "network"), ("row_dex", "dex"),
                            ("row_price", "price"), ("row_liquidity", "liquidity")]:
            row = tk.Frame(pad, bg=PANEL)
            row.pack(fill="x", pady=4)
            cap = tk.Label(row, bg=PANEL, fg=MUTED, font=(MONO, 8, "bold"), anchor="w")
            cap.pack(anchor="w")
            val = tk.Label(row, text="—", bg=PANEL, fg=TEXT, font=("Consolas", 11, "bold"), anchor="w")
            val.pack(anchor="w")
            self.token_rows[field] = (key, cap, val)
        self.meta_labels = self.token_rows  # обратная совместимость с update_meta()

        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=(4, 10))
        bundle_row = tk.Frame(pad, bg=PANEL)
        bundle_row.pack(fill="x")
        self.bundle_row_cap = tk.Label(bundle_row, bg=PANEL, fg=MUTED, font=(MONO, 8, "bold"), anchor="w")
        self.bundle_row_cap.pack(anchor="w")
        self.bundle_row_val = tk.Label(bundle_row, text="—", bg=PANEL, fg=TEXT,
                                        font=("Consolas", 11, "bold"), anchor="w")
        self.bundle_row_val.pack(anchor="w")

    def _build_new_pairs_pane(self, holder):
        """Список свежесозданных пулов и вкладка Migrated."""
        for key in ("tab_new_pairs", "tab_migrated"):
            pane = tk.Frame(holder, bg=PANEL, padx=10, pady=10)
            self.left_panes[key] = pane

        pane = self.left_panes["tab_new_pairs"]
        self.pairs_hint = tk.Label(pane, bg=PANEL, fg=MUTED, font=(MONO, 7),
                                    anchor="w", justify="left", wraplength=230)
        self.pairs_hint.pack(fill="x", pady=(0, 6))

        table = tk.Frame(pane, bg=PANEL)
        table.pack(fill="both", expand=True)
        self.pairs_tree = ttk.Treeview(table, columns=("token", "age"), show="headings",
                                        style="Treeview", height=9)
        self.pairs_tree.column("token", width=140, anchor="w", stretch=True)
        self.pairs_tree.column("age", width=70, anchor="e", stretch=False)
        self.pairs_tree.heading("token", text="", anchor="w")
        self.pairs_tree.heading("age", text="", anchor="e")
        self.pairs_tree.tag_configure("fresh", foreground=ACCENT)
        self.pairs_tree.tag_configure("older", foreground=TEXT)
        self.pairs_tree.tag_configure("placeholder", foreground=MUTED)
        self.pairs_tree.bind("<Double-Button-1>", self.on_pair_double_click)
        vsb = ttk.Scrollbar(table, orient="vertical", command=self.pairs_tree.yview)
        self.pairs_tree.configure(yscrollcommand=vsb.set)
        self.pairs_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._pairs_rows = {}

        self.migrated_lbl = tk.Label(self.left_panes["tab_migrated"], bg=PANEL, fg=MUTED,
                                      font=(MONO, 8), anchor="nw", justify="left",
                                      wraplength=230)
        self.migrated_lbl.pack(fill="both", expand=True)

    def select_left_tab(self, key):
        if self._active_left_tab == key:
            return
        for pane in self.left_panes.values():
            pane.pack_forget()
        self.left_panes[key].pack(fill="both", expand=True)
        self._active_left_tab = key
        for tab_key, btn in self.left_tabs.items():
            active = tab_key == key
            btn.configure(fg=ON_ACCENT if active else MUTED,
                           bg=ACCENT if active else PANEL)
        if key == "tab_new_pairs":
            self.refresh_new_pairs()

    def _build_bundle_card(self, parent):
        """Главная панель приложения — результат анализа бандлов."""
        card = self._card(parent, 1, weight=1)
        pad = tk.Frame(card, bg=PANEL, padx=16, pady=14)
        pad.pack(fill="both", expand=True)

        head = tk.Frame(pad, bg=PANEL)
        head.pack(fill="x")
        self.bundle_card_title = tk.Label(head, bg=PANEL, fg=ACCENT, font=(MONO, 8, "bold"))
        self.bundle_card_title.pack(side="left")
        self.bundle_window_lbl = tk.Label(head, bg=PANEL, fg=MUTED, font=(MONO, 8))
        self.bundle_window_lbl.pack(side="right")

        summary = tk.Frame(pad, bg=PANEL)
        summary.pack(fill="x", pady=(10, 0))

        big_box = tk.Frame(summary, bg=PANEL)
        big_box.pack(side="left")

        pair = tk.Frame(big_box, bg=PANEL)
        pair.pack(anchor="w")

        bought_box = tk.Frame(pair, bg=PANEL)
        bought_box.pack(side="left")
        self.bundle_big_cap = tk.Label(bought_box, bg=PANEL, fg=MUTED,
                                        font=(MONO, 8, "bold"), anchor="w")
        self.bundle_big_cap.pack(anchor="w")
        self.bundle_big_val = tk.Label(bought_box, text="—", bg=PANEL, fg=TEXT,
                                        font=("Consolas", 38, "bold"), anchor="w")
        self.bundle_big_val.pack(anchor="w")

        # цифра слева — снимок запуска, она не может меняться; справа — сколько
        # из этого бандл держит прямо сейчас, и вот она живая
        tk.Label(pair, text="→", bg=PANEL, fg=MUTED,
                 font=("Consolas", 22, "bold")).pack(side="left", padx=14, pady=(14, 0))

        held_box = tk.Frame(pair, bg=PANEL)
        held_box.pack(side="left")
        self.bundle_held_cap = tk.Label(held_box, bg=PANEL, fg=MUTED,
                                         font=(MONO, 8, "bold"), anchor="w")
        self.bundle_held_cap.pack(anchor="w")
        self.bundle_held_val = tk.Label(held_box, text="—", bg=PANEL, fg=MUTED,
                                         font=("Consolas", 38, "bold"), anchor="w")
        self.bundle_held_val.pack(anchor="w")

        self.bundle_verdict_lbl = tk.Label(big_box, text="", bg=PANEL, fg=MUTED,
                                            font=(MONO, 11, "bold"), anchor="w")
        self.bundle_verdict_lbl.pack(anchor="w")

        # три подписанные цифры вместо одной строки текста: сразу понятно,
        # что означает большое число слева и на чём оно построено
        stats = tk.Frame(summary, bg=PANEL)
        stats.pack(side="right", anchor="n", pady=(6, 0))
        self.bundle_stats = {}
        for key, color in (("bundle_stat_early", GOLD),
                            ("bundle_stat_wallets", TEXT),
                            ("bundle_stat_groups", ACCENT)):
            box = tk.Frame(stats, bg=PANEL)
            box.pack(side="left", padx=(26, 0))
            val = tk.Label(box, text="—", bg=PANEL, fg=color,
                            font=("Consolas", 17, "bold"), anchor="e")
            val.pack(anchor="e")
            cap = tk.Label(box, bg=PANEL, fg=MUTED, font=(MONO, 8, "bold"), anchor="e")
            cap.pack(anchor="e")
            self.bundle_stats[key] = (cap, val)

        # Вердикт по риску живёт в широкой центральной панели: в узкой левой
        # карточке те же причины разъезжались на четыре строки и вытягивали
        # окно так, что нижнюю полосу срезало.
        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=(12, 10))
        risk_box = tk.Frame(pad, bg=PANEL)
        risk_box.pack(fill="x")

        risk_head = tk.Frame(risk_box, bg=PANEL)
        risk_head.pack(fill="x")
        self.risk_cap = tk.Label(risk_head, bg=PANEL, fg=ACCENT,
                                  font=(MONO, 8, "bold"))
        self.risk_cap.pack(side="left", pady=(4, 0))
        self.risk_score_lbl = tk.Label(risk_head, text="—", bg=PANEL, fg=MUTED,
                                        font=(MONO, 20, "bold"))
        self.risk_score_lbl.pack(side="left", padx=(14, 0))
        self.risk_level_lbl = tk.Label(risk_head, text="", bg=PANEL, fg=MUTED,
                                        font=(MONO, 11, "bold"))
        self.risk_level_lbl.pack(side="left", padx=(12, 0), pady=(4, 0))
        self.risk_note_lbl = tk.Label(risk_head, bg=PANEL, fg=FAINT, font=(MONO, 7))
        self.risk_note_lbl.pack(side="right", pady=(6, 0))

        # полоса: число само по себе не даёт почувствовать, насколько это много
        self.risk_bar = tk.Canvas(risk_box, height=6, bg=PANEL2, highlightthickness=0)
        self.risk_bar.pack(fill="x", pady=(6, 0))
        self._risk_bar_rect = self.risk_bar.create_rectangle(0, 0, 0, 6, fill=MUTED, outline="")
        self.risk_bar.bind("<Configure>", lambda e: self._redraw_risk_bar())
        self._risk_score = None

        # причины перечисляем всегда: вердикт без объяснения — чёрный ящик
        self.risk_reasons_lbl = tk.Label(risk_box, text="", bg=PANEL, fg=MUTED,
                                          font=(MONO, 8), anchor="w",
                                          justify="left")
        self.risk_reasons_lbl.pack(fill="x", pady=(5, 0))
        tk.Frame(pad, bg=BORDER, height=1).pack(fill="x", pady=12)

        list_head = tk.Frame(pad, bg=PANEL)
        list_head.pack(fill="x", pady=(0, 6))
        self.bundle_list_title = tk.Label(list_head, bg=PANEL, fg=ACCENT,
                                           font=(MONO, 8, "bold"))
        self.bundle_list_title.pack(side="left")
        self.bundle_list_hint = tk.Label(list_head, bg=PANEL, fg=MUTED, font=(MONO, 8))
        self.bundle_list_hint.pack(side="right")

        table_frame = tk.Frame(pad, bg=PANEL)
        table_frame.pack(fill="both", expand=True)
        cols = ("group", "wallet", "pct", "now", "amount", "funder")
        self.bundle_tree = ttk.Treeview(table_frame, columns=cols, show="headings",
                                         style="Treeview", height=4)
        self.bundle_tree.column("group", width=58, anchor="center", stretch=False)
        self.bundle_tree.column("wallet", width=200, anchor="w", stretch=True)
        self.bundle_tree.column("pct", width=100, anchor="e", stretch=False)
        self.bundle_tree.column("now", width=95, anchor="e", stretch=False)
        self.bundle_tree.column("amount", width=120, anchor="e", stretch=False)
        self.bundle_tree.column("funder", width=180, anchor="w", stretch=False)
        # кошельки одной группы подсвечены одинаково, соседние группы — разными
        # оттенками, чтобы связка читалась глазом, а не только по номеру
        for idx, (bg_color, fg_color) in enumerate(GROUP_TINTS, start=1):
            self.bundle_tree.tag_configure(f"g{idx}", foreground=fg_color, background=bg_color)
        self.bundle_tree.tag_configure("solo", foreground=TEXT, background=PANEL)
        self.bundle_tree.tag_configure("solo_alt", foreground=TEXT, background=PANEL2)
        self.bundle_tree.tag_configure("placeholder", foreground=MUTED)
        self.bundle_tree.tag_configure("exited", foreground=EXITED)
        self.bundle_tree.bind("<Double-Button-1>", self.on_bundle_row_double_click)
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.bundle_tree.yview)
        self.bundle_tree.configure(yscrollcommand=vsb.set)
        self.bundle_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._bundle_row_data = {}
        self._bundle_placeholder_key = None
        self._bundle_last_result = None
        self._bundle_wallet_rows = {}   # кошелёк -> строка таблицы, для живого обновления
        self._bundle_held = {}          # кошелёк -> % предложения на нём сейчас
        self._bundle_held_logged = None
        self._bundle_big_cap_key = "bundle_stat_bundled"

    def _build_bottom_strip(self):
        """Второстепенная полоса: компактный график цены + компактная лента сделок."""
        strip = ttk.Frame(self.root, padding=(18, 0, 18, 6))
        strip.pack(fill="x")
        strip.grid_columnconfigure(0, weight=2, uniform="strip")
        strip.grid_columnconfigure(1, weight=3, uniform="strip")

        chart_outer = tk.Frame(strip, bg=BORDER)
        chart_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        chart_card = tk.Frame(chart_outer, bg=PANEL)
        chart_card.pack(fill="both", expand=True, padx=2, pady=2)

        chart_head = tk.Frame(chart_card, bg=PANEL, padx=10, pady=6)
        chart_head.pack(fill="x")
        self.feed_card_title = tk.Label(chart_head, bg=PANEL, fg=ACCENT, font=(MONO, 8, "bold"))
        self.feed_card_title.pack(side="left")
        price_box = tk.Frame(chart_head, bg=PANEL)
        price_box.pack(side="right")
        self.last_price_cap = tk.Label(price_box, bg=PANEL, fg=MUTED, font=(MONO, 7, "bold"), anchor="e")
        self.last_price_cap.pack(anchor="e")
        self.last_price_val = tk.Label(price_box, text="—", bg=PANEL, fg=GREEN,
                                        font=("Consolas", 13, "bold"), anchor="e")
        self.last_price_val.pack(anchor="e")

        self.spark_canvas = tk.Canvas(chart_card, bg=PANEL, height=104, highlightthickness=0)
        self.spark_canvas.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.spark_placeholder = self.spark_canvas.create_text(
            10, 60, anchor="w", fill=MUTED, font=(MONO, 9), text=""
        )
        self.spark_canvas.bind("<Configure>", lambda e: self._redraw_candles())

        feed_outer = tk.Frame(strip, bg=BORDER)
        feed_outer.grid(row=0, column=1, sticky="nsew")
        feed_card = tk.Frame(feed_outer, bg=PANEL)
        feed_card.pack(fill="both", expand=True, padx=2, pady=2)

        feed_head = tk.Frame(feed_card, bg=PANEL, padx=10, pady=6)
        feed_head.pack(fill="x")
        self.trades_title = tk.Label(feed_head, bg=PANEL, fg=ACCENT, font=(MONO, 8, "bold"))
        self.trades_title.pack(side="left")

        table_frame = tk.Frame(feed_card, bg=PANEL)
        table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        columns = ("time", "type", "wallet", "amount", "value", "tx")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings",
                                  style="Treeview", height=5)
        for col, w, anchor in [
            ("time", 62, "center"), ("type", 78, "center"), ("wallet", 130, "w"),
            ("amount", 110, "e"), ("value", 90, "e"), ("tx", 110, "w"),
        ]:
            self.tree.column(col, width=w, anchor=anchor, stretch=(col in ("wallet", "tx")))
        # два оттенка на каждый тип — соседние строки чуть отличаются фоном,
        # иначе длинная лента сливается в сплошное цветное полотно
        self.tree.tag_configure("buy", foreground=GREEN, background=ROW_BUY)
        self.tree.tag_configure("buy_alt", foreground=GREEN, background=ROW_BUY_ALT)
        self.tree.tag_configure("sell", foreground=RED, background=ROW_SELL)
        self.tree.tag_configure("sell_alt", foreground=RED, background=ROW_SELL_ALT)
        self.tree.bind("<Double-Button-1>", self.on_row_double_click)
        self.tree.bind("<Motion>", self.on_row_hover)

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")


    def set_language(self, code):
        if code not in LANG_NAMES:
            return
        self.tr.lang = code
        self.lang_var.set(LANG_NAMES[code])
        self._refresh_lang_buttons()
        self.retranslate()

    def _refresh_lang_buttons(self):
        for code, btn in self.lang_buttons.items():
            active = code == self.tr.lang
            btn.configure(bg=ACCENT if active else PANEL2,
                           fg=ON_ACCENT if active else MUTED)

    def retranslate(self):
        t = self.tr.t
        self.root.title(t("app_title"))
        if not self.worker:
            self.subtitle_lbl.configure(text=t("app_subtitle"))
        self.lang_lbl.configure(text=t("lang_label"))
        if self._ca_placeholder_on:  # подсказка внутри поля тоже переводится
            self._ca_placeholder_on = False
            self.ca_entry.delete(0, "end")
            self._show_ca_placeholder()
        self.start_btn.configure(text=t("start"))
        self.stop_btn.configure(text=t("stop"))
        self.clear_btn.configure(text=t("clear"))
        self.bundle_row_cap.configure(text=t("row_bundle"))
        self.risk_cap.configure(text=t("row_risk"))
        self.risk_note_lbl.configure(text=t("risk_disclaimer"))
        self._render_risk()
        if not self.worker:
            self.bundle_row_val.configure(text="—")
        self.status_var.set(t("status_ready") if not self.worker else t("status_running"))

        self.live_lbl.configure(text=t("live") if self._live_on else t("offline"))
        self.header_buys_cap.configure(text=t("header_stat_buys"))
        self.header_sells_cap.configure(text=t("header_stat_sells"))
        self.header_clock_cap.configure(text=t("header_stat_clock"))

        self.token_card_title.configure(text=t("card_token_info"))
        for key, btn in self.left_tabs.items():
            btn.configure(text=t(key))
        self.migrated_lbl.configure(text=t("migrated_todo"))
        self.pairs_hint.configure(text=t("pairs_hint", n=len(self._pairs_rows)))
        self.pairs_tree.heading("token", text=t("col_pair_token"), anchor="w")
        self.pairs_tree.heading("age", text=t("col_pair_age"), anchor="e")
        self.feed_card_title.configure(text=t("card_live_feed"))
        self.bundle_card_title.configure(text=t("card_bundle_analysis"))
        self.trades_title.configure(text=t("card_trades"))
        self.bundle_window_lbl.configure(text=t("bundle_window_fmt", w=BUNDLE_WINDOW_SECONDS))
        self.bundle_big_cap.configure(text=t(self._bundle_big_cap_key))
        self.bundle_held_cap.configure(text=t("bundle_still_held"))
        self.bundle_list_title.configure(text=t("bundle_list_title", w=BUNDLE_WINDOW_SECONDS))
        self.bundle_list_hint.configure(text=t("bundle_list_hint"))
        for key, (cap, _val) in self.bundle_stats.items():
            cap.configure(text=t(key))
        # заголовки выравниваем по своим колонкам, иначе подпись висит по центру
        # над прижатым влево содержимым
        self.bundle_tree.heading("group", text=t("col_group"), anchor="center")
        self.bundle_tree.heading("wallet", text=t("col_buyer"), anchor="w")
        self.bundle_tree.heading("pct", text=t("col_supply_pct"), anchor="e")
        self.bundle_tree.heading("now", text=t("col_now"), anchor="e")
        self.bundle_tree.heading("amount", text=t("col_bought"), anchor="e")
        self.bundle_tree.heading("funder", text=t("col_funder"), anchor="w")
        if self._bundle_placeholder_key:  # подсказка тоже должна переводиться
            self.clear_bundle_table(self._bundle_placeholder_key)
        elif self._bundle_last_result:   # и сама таблица — тоже
            self._render_bundle_rows(self._bundle_last_result)
        self.last_price_cap.configure(text=t("last_price_label"))

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
            if any(tag.startswith("buy") for tag in tags):
                vals[1] = "▲ " + t("trade_buy")
            elif any(tag.startswith("sell") for tag in tags):
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
                    self._show_ca_placeholder()
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
                elif kind == "bundle_funders":
                    self.show_bundle_result(payload, keep_holdings=True)
                elif kind == "bundle_holdings":
                    self.update_bundle_holdings(payload)
                elif kind == "new_pairs":
                    self.show_new_pairs(payload)
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
        base_tag = "buy" if is_buy else "sell"
        tag_type = base_tag if self._row_count % 2 == 0 else base_tag + "_alt"
        arrow = "▲" if is_buy else "▼"
        label = f"{arrow} " + (t("trade_buy") if is_buy else t("trade_sell"))
        self._row_count += 1

        wallet = data["wallet"]
        wallet_short = wallet if len(wallet) <= 18 else f"{wallet[:8]}…{wallet[-6:]}"
        tx_short = data["tx"] if len(data["tx"]) <= 18 else f"{data['tx'][:8]}…{data['tx'][-6:]}"
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
        """Складывает цены в секундные свечи. Секунды без сделок не пропускаются,
        а заполняются "плоскими" свечами по последней цене — иначе на графике
        появлялись дыры вместо непрерывной ленты, как на биржевом терминале."""
        bucket = int(time.time() // self.candle_seconds)
        self._fill_candle_gaps(bucket)

        if self.candles and self.candles[-1]["bucket"] == bucket:
            c = self.candles[-1]
            c["high"] = max(c["high"], price)
            c["low"] = min(c["low"], price)
            c["close"] = price
        else:
            self.candles.append({
                "bucket": bucket, "open": price, "high": price, "low": price, "close": price,
            })
        self._trim_candles()

    def _fill_candle_gaps(self, up_to_bucket):
        """Достраивает пустые секунды свечами по последней цене, включая текущую —
        иначе график всё время отставал бы на секунду. Пришедшая следом сделка
        просто обновит high/low/close у уже созданной свечи."""
        if not self.candles:
            return
        last = self.candles[-1]
        gap = up_to_bucket - last["bucket"]
        if gap <= 0:
            return
        price = last["close"]
        for i in range(1, min(gap, self.max_candles) + 1):
            self.candles.append({
                "bucket": last["bucket"] + i,
                "open": price, "high": price, "low": price, "close": price,
            })

    def _trim_candles(self):
        if len(self.candles) > self.max_candles:
            self.candles = self.candles[-self.max_candles:]

    def _tick_candles(self):
        """Двигает график во времени, даже когда сделок нет."""
        if self._live_on and self.candles:
            self._fill_candle_gaps(int(time.time() // self.candle_seconds))
            self._trim_candles()
            self._redraw_candles()
        self.root.after(1000, self._tick_candles)

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
        self.last_price_val.configure(text="—", fg=GREEN)
        self.bundle_row_val.configure(text="—", fg=TEXT)
        self.bundle_big_val.configure(text="—", fg=TEXT)
        self.bundle_verdict_lbl.configure(text="", fg=MUTED)
        self.bundle_held_val.configure(text="—", fg=MUTED)
        self._stop_holdings_tracker()
        self._bundle_held.clear()
        self._bundle_held_logged = None
        self._bundle_last_result = None
        self._render_risk()
        for key in self.bundle_stats:
            self._set_bundle_stat(key, "—")
        self.clear_bundle_table("bundle_table_idle")
        self._redraw_candles()

    def start(self):
        ca = self.ca_text()
        if not ca:
            self.status_var.set(self.tr.t("status_enter_ca"))
            return
        # частота фиксированная и максимально быстрая: цикл сам притормозит,
        # если RPC начнёт ограничивать, и вернётся обратно
        interval = POLL_INTERVAL
        rpc_override = RPC_OVERRIDE

        self.clear()
        for field, (key, cap, val) in self.token_rows.items():
            val.configure(text="—")
        self.token_name_lbl.configure(text="—")
        self.token_symbol_lbl.configure(text="")
        self.token_icon.configure(text="?")

        self.select_left_tab("tab_token")
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
        self._show_ca_placeholder()
        self.stop_btn.configure(state="disabled")
        self._stop_holdings_tracker()  # Стоп гасит и фоновое перечитывание балансов

    def start_bundle_check(self, ca, rpc_override=None):
        if self._bundle_stop_event:
            self._bundle_stop_event.set()  # прерываем предыдущую проверку, если ещё бежит
        self._stop_holdings_tracker()

        self._bundle_stop_event = threading.Event()
        bundle_stop_event = self._bundle_stop_event
        tr = self.tr

        self.bundle_row_val.configure(text=tr.t("bundle_checking_short"), fg=MUTED)
        self.bundle_big_val.configure(text="…", fg=MUTED)
        self.bundle_verdict_lbl.configure(text=tr.t("bundle_verdict_checking"), fg=MUTED)
        self._bundle_last_result = None
        for key in self.bundle_stats:
            self._set_bundle_stat(key, "…")
        self.clear_bundle_table("bundle_table_checking")

        def worker():
            try:
                run_bundle_check(ca, self.emit, tr, bundle_stop_event, rpc_override=rpc_override)
            except Exception as e:
                self.emit("bundle_result", {"error": tr.t("log_unexpected_error", e=e)})

        threading.Thread(target=worker, daemon=True).start()

    def clear_bundle_table(self, placeholder_key=None):
        for row_id in self.bundle_tree.get_children():
            self.bundle_tree.delete(row_id)
        self._bundle_row_data.clear()
        self._bundle_wallet_rows.clear()
        # пустая таблица без пояснения выглядит как будто что-то сломалось,
        # поэтому всегда показываем строку-подсказку о текущем состоянии
        self._bundle_placeholder_key = placeholder_key
        if placeholder_key:
            self.bundle_tree.insert("", "end",
                                     values=("", self.tr.t(placeholder_key), "", "", "", ""),
                                     tags=("placeholder",))

    def _set_bundle_stat(self, key, text, color=None):
        cap, val = self.bundle_stats[key]
        val.configure(text=text)
        if color:
            val.configure(fg=color)

    def _render_bundle_rows(self, data):
        """Рисует список ранних покупателей — это и есть главный ответ программы:
        кто именно закупился на запуске и какие кошельки связаны между собой."""
        t = self.tr.t
        rows = data.get("wallet_rows") or []
        if not rows:
            self.clear_bundle_table("bundle_table_clean")
            return

        for row_id in self.bundle_tree.get_children():
            self.bundle_tree.delete(row_id)
        self._bundle_row_data.clear()
        self._bundle_wallet_rows.clear()
        self._bundle_placeholder_key = None

        solo_index = 0
        for row in rows:
            wallet = row["wallet"]
            short_wallet = wallet if len(wallet) <= 22 else f"{wallet[:10]}…{wallet[-8:]}"
            group = row.get("group")
            funder = row.get("funder")
            if group:
                group_text = t("bundle_group_fmt", n=group)
                tag = f"g{(group - 1) % 4 + 1}"
            else:
                group_text = t("bundle_group_alone")
                tag = "solo" if solo_index % 2 == 0 else "solo_alt"
                solo_index += 1
            if funder:
                funder_text = funder if len(funder) <= 20 else f"{funder[:8]}…{funder[-6:]}"
                if row.get("hops") == 2:
                    funder_text = "↳ " + funder_text   # связь через промежуточный кошелёк
            elif row.get("checked"):
                funder_text = t("bundle_funder_none")
            else:
                funder_text = t("bundle_funder_skipped")

            held = self._bundle_held.get(wallet)
            tag_list = (tag,)
            if held is None:
                now_text = "—"          # баланс ещё не прочитан
            elif held < 0.0005:
                now_text = t("bundle_row_sold")
                tag_list = (tag, "exited")
            else:
                now_text = f"{held:.2f}%"

            new_id = self.bundle_tree.insert(
                "", "end",
                values=(group_text, short_wallet, f"{row['pct']:.2f}%", now_text,
                        human_number(row["amount"]), funder_text),
                tags=tag_list,
            )
            self._bundle_row_data[new_id] = {"wallet": wallet, "funder": funder}
            self._bundle_wallet_rows[wallet] = new_id

    # -- живое отслеживание остатков на кошельках бандла -------------------
    def _start_holdings_tracker(self, track, rows):
        self._stop_holdings_tracker()
        grouped = [r["wallet"] for r in rows if r.get("group")]
        others = [r["wallet"] for r in rows if not r.get("group")]
        # кошельки бандла — обязательно, остальные добираем сверху списка:
        # каждый кошелёк это отдельный запрос, а публичный RPC не резиновый
        wallets = grouped + others[:max(0, 120 - len(grouped))]
        if not wallets:
            return
        self._holdings_stop = threading.Event()
        stop_event = self._holdings_stop
        threading.Thread(
            target=lambda: track_bundle_holdings(track, wallets, self.emit, stop_event),
            daemon=True,
        ).start()

    def _stop_holdings_tracker(self):
        if self._holdings_stop:
            self._holdings_stop.set()
            self._holdings_stop = None

    def update_bundle_holdings(self, data):
        held = data.get("held_pct") or {}
        if not held:
            return
        self._bundle_held.update(held)
        t = self.tr.t
        for wallet, pct in held.items():
            row_id = self._bundle_wallet_rows.get(wallet)
            if not row_id or not self.bundle_tree.exists(row_id):
                continue
            values = list(self.bundle_tree.item(row_id, "values"))
            sold_out = pct < 0.0005
            values[3] = t("bundle_row_sold") if sold_out else f"{pct:.2f}%"
            tags = [tag for tag in self.bundle_tree.item(row_id, "tags") if tag != "exited"]
            if sold_out:
                tags.append("exited")
            self.bundle_tree.item(row_id, values=values, tags=tuple(tags))
        self._refresh_bundle_held_total()
        self._render_risk()

    def _refresh_bundle_held_total(self):
        data = self._bundle_last_result or {}
        all_rows = data.get("wallet_rows") or []
        grouped = [r for r in all_rows if r.get("group")]
        # правая цифра всегда считает ровно тот же набор кошельков, что и левая:
        # есть группы — только их, нет групп — всех ранних покупателей
        if grouped:
            rows, bought = grouped, (data.get("bundle_pct") or 0.0)
        else:
            rows, bought = all_rows, (data.get("early_pct") or 0.0)
        known = [r for r in rows if r["wallet"] in self._bundle_held]
        if not known:
            self.bundle_held_val.configure(text="—", fg=MUTED)
            return
        held_pct = sum(self._bundle_held[r["wallet"]] for r in known)
        # цвет по доле оставшегося: держат почти всё — навес никуда не делся
        ratio = (held_pct / bought) if bought else 0.0
        color = RED if ratio >= 0.66 else (GOLD if ratio >= 0.33 else GREEN)
        # часть кошельков могла не дочитаться — тогда честнее показать "не меньше"
        prefix = "" if len(known) == len(rows) else "≥"
        self.bundle_held_val.configure(text=f"{prefix}{held_pct:.1f}%", fg=color)

        still_in = sum(1 for r in known if self._bundle_held[r["wallet"]] >= 0.0005)
        if self._bundle_held_logged != (round(held_pct, 2), still_in):
            self._bundle_held_logged = (round(held_pct, 2), still_in)
            self.append_log(self.tr.t("bundle_held_log", pct=held_pct,
                                       left=still_in, total=len(rows)), "info")

    def _render_risk(self):
        """Перерисовывает вердикт по риску из последнего результата и текущих
        остатков на кошельках — вызывается и при смене языка, и при каждом
        обновлении балансов."""
        t = self.tr.t
        data = self._bundle_last_result
        if not data:
            self.risk_score_lbl.configure(text="—", fg=MUTED)
            self.risk_level_lbl.configure(text=t("risk_level_none"), fg=MUTED)
            self.risk_reasons_lbl.configure(text=t("risk_score_hint"))
            self._risk_score = None
            self._redraw_risk_bar()
            return

        risk = assess_token_risk(data, self._bundle_held)
        color = {"high": RED, "caution": GOLD, "low": GREEN}[risk["level"]]
        if data.get("funders_pending"):
            # часть сигналов ещё не посчитана — вердикт был бы преждевременным
            color = MUTED
            self.risk_score_lbl.configure(text=f"{risk['score']}%", fg=MUTED)
            self.risk_level_lbl.configure(text=t("bundle_verdict_checking"), fg=MUTED)
        else:
            self.risk_score_lbl.configure(text=f"{risk['score']}%", fg=color)
            self.risk_level_lbl.configure(text=t("risk_level_" + risk["level"]), fg=color)
        self._risk_score, self._risk_color = risk["score"], color
        self._redraw_risk_bar()
        if risk["reasons"]:
            # рядом с каждой причиной — сколько именно баллов она сняла
            lines = [f"•  −{penalty:.0f}   {t(key, **kwargs)}"
                     for penalty, key, kwargs in risk["reasons"]]
        else:
            lines = [f"•  {t('risk_clean')}"]
        self.risk_reasons_lbl.configure(text="\n".join(lines))

    # -- новые пары ------------------------------------------------------
    def refresh_new_pairs(self, force=False):
        """Тянет список новых пулов в фоне; чаще раза в 15 секунд не дёргаем RPC."""
        now = time.time()
        if not force and now - getattr(self, "_pairs_fetched_at", 0) < 15:
            return
        if getattr(self, "_pairs_busy", False):
            return
        self._pairs_busy = True
        self._pairs_fetched_at = now
        if not self._pairs_rows:
            self._set_pairs_placeholder("pairs_loading")

        def worker():
            try:
                rpc_url = RPC_OVERRIDE or DEFAULT_EVM_RPCS["robinhood"]
                pairs = fetch_new_pairs(rpc_url, KNOWN_POOL_MANAGERS["robinhood"])
                # названия читаем только для показанных строк, пачкой
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
                    future_map = {pool.submit(evm_get_token_identity, rpc_url, p["token"]): p
                                   for p in pairs[:25]}
                    for fut in concurrent.futures.as_completed(future_map):
                        try:
                            _name, symbol = fut.result()
                        except Exception:
                            symbol = None
                        future_map[fut]["symbol"] = symbol
                self.emit("new_pairs", {"pairs": pairs[:25]})
            except Exception as e:
                self.emit("new_pairs", {"error": str(e)})

        threading.Thread(target=worker, daemon=True).start()

    def _tick_new_pairs(self):
        # обновляем только когда вкладка открыта — иначе это лишняя нагрузка на RPC
        if self._active_left_tab == "tab_new_pairs":
            self.refresh_new_pairs()
        self.root.after(15000, self._tick_new_pairs)

    def _set_pairs_placeholder(self, key):
        for row_id in self.pairs_tree.get_children():
            self.pairs_tree.delete(row_id)
        self._pairs_rows.clear()
        self.pairs_tree.insert("", "end", values=(self.tr.t(key), ""), tags=("placeholder",))

    def show_new_pairs(self, data):
        self._pairs_busy = False
        if data.get("error"):
            self._set_pairs_placeholder("pairs_failed")
            return
        pairs = data.get("pairs") or []
        if not pairs:
            self._set_pairs_placeholder("pairs_empty")
            return

        for row_id in self.pairs_tree.get_children():
            self.pairs_tree.delete(row_id)
        self._pairs_rows.clear()
        for pair in pairs:
            age = pair["age_seconds"]
            age_text = f"{age:.0f}с" if age < 60 else f"{age / 60:.0f}м"
            symbol = pair.get("symbol") or f"{pair['token'][:8]}…"
            row_id = self.pairs_tree.insert(
                "", "end", values=(symbol, age_text),
                tags=("fresh" if age < 300 else "older",))
            self._pairs_rows[row_id] = pair
        self.pairs_hint.configure(text=self.tr.t("pairs_hint", n=len(pairs)))

    def on_pair_double_click(self, event):
        pair = self._pairs_rows.get(self.pairs_tree.identify_row(event.y))
        if not pair:
            return
        if self.worker:
            self.stop()
        self._hide_ca_placeholder()
        self.ca_entry.configure(state="normal")
        self.ca_entry.delete(0, "end")
        self.ca_entry.insert(0, pair["token"])
        self.select_left_tab("tab_token")   # дальше человек смотрит на разбор токена
        self.start()

    def _redraw_risk_bar(self):
        width = self.risk_bar.winfo_width()
        if width <= 1:
            return
        if self._risk_score is None:
            self.risk_bar.coords(self._risk_bar_rect, 0, 0, 0, 6)
            return
        self.risk_bar.coords(self._risk_bar_rect, 0, 0, width * self._risk_score / 100, 6)
        self.risk_bar.itemconfigure(self._risk_bar_rect, fill=getattr(self, "_risk_color", MUTED))

    def show_bundle_result(self, data, keep_holdings=False):
        """keep_holdings=True — это второй, догоняющий результат с раздатчиками:
        панель обновляется на месте, уже собранные балансы и запущенный трекер
        трогать нельзя, иначе всё начнётся заново."""
        t = self.tr.t
        if not keep_holdings:
            self._stop_holdings_tracker()
            self._bundle_held.clear()
            self._bundle_held_logged = None
            self.bundle_held_val.configure(text="—", fg=MUTED)
        self._bundle_last_result = None
        self._render_risk()
        self.clear_bundle_table()

        if data.get("error"):
            self.append_log(data["error"], "error")
            self.bundle_row_val.configure(text=t("bundle_row_na"), fg=MUTED)
            self.bundle_big_val.configure(text="—", fg=MUTED)
            self.bundle_verdict_lbl.configure(text=t("bundle_verdict_na"), fg=MUTED)
            for key in self.bundle_stats:
                self._set_bundle_stat(key, "—")
            self.clear_bundle_table("bundle_table_idle")
            return

        pending = bool(data.get("funders_pending"))
        clusters = data.get("bundle_clusters") or {}

        if not keep_holdings:
            self.append_log(f"— {t('bundle_result_title')} —", "info")
            self.append_log(
                t("bundle_result_early", window=data["window_seconds"],
                  pct=data["early_pct"], wallets=data["early_wallets"]),
                "info",
            )

        self._set_bundle_stat("bundle_stat_early", f"{data['early_pct']:.1f}%")
        self._set_bundle_stat("bundle_stat_wallets", str(data["early_wallets"]))
        self._set_bundle_stat("bundle_stat_groups", "…" if pending else str(len(clusters)),
                              RED if clusters else ACCENT)

        self._bundle_last_result = data
        self._render_bundle_rows(data)
        if keep_holdings and self._bundle_held:
            # связи дочитались — "ещё держат" теперь считается по кошелькам бандла,
            # а не по всем ранним; без пересчёта до следующего обновления балансов
            # висела прежняя цифра, и она оказывалась больше самого бандла
            self._refresh_bundle_held_total()
        self._render_risk()
        if data.get("track") and data.get("wallet_rows") and not keep_holdings:
            self._start_holdings_tracker(data["track"], data["wallet_rows"])

        self._bundle_big_cap_key = "bundle_stat_bundled" if clusters else "bundle_stat_early"
        self.bundle_big_cap.configure(text=t(self._bundle_big_cap_key))

        if pending:
            # связи ещё считаются: пока нельзя ни обвинять, ни оправдывать
            self.bundle_big_val.configure(text=f"{data['early_pct']:.1f}%", fg=TEXT)
            self.bundle_verdict_lbl.configure(text=t("bundle_verdict_checking"), fg=MUTED)
            self.bundle_row_val.configure(text=t("bundle_checking_short"), fg=MUTED)
        elif data.get("funder_unsupported"):
            self.append_log(t("bundle_funder_unsupported_note"), "info")
            self.bundle_row_val.configure(
                text=t("bundle_row_early_only", pct=data["early_pct"]), fg=TEXT)
            self.bundle_big_val.configure(text=f"{data['early_pct']:.1f}%", fg=GOLD)
            self.bundle_verdict_lbl.configure(text=t("bundle_verdict_early_only"), fg=GOLD)
        elif clusters:
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
        else:
            self.append_log(t("bundle_result_none"), "info")
            self.bundle_big_val.configure(text=f"{data['early_pct']:.1f}%", fg=GREEN)
            self.bundle_verdict_lbl.configure(text=t("bundle_verdict_clean"), fg=GREEN)
            self.bundle_row_val.configure(text=t("bundle_row_clean"), fg=GREEN)

        if data.get("truncated") and not keep_holdings:
            self.append_log(t("bundle_result_cap_note", n=25), "info")

    def on_bundle_row_double_click(self, event):
        row_id = self.bundle_tree.identify_row(event.y)
        info = self._bundle_row_data.get(row_id)
        if not info:
            return
        value = info.get("wallet") or info.get("funder")
        if not value:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.status_var.set(self.tr.t("copied", value=value))

    def on_close(self):
        if self.stop_event:
            self.stop_event.set()
        if self._bundle_stop_event:
            self._bundle_stop_event.set()
        self._stop_holdings_tracker()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
