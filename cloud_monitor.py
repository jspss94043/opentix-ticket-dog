from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright


URL = "https://www.opentix.life/event/2076925048527581185"
STATE_FILE = Path("cloud_state.json")

EXCLUDED_WORDS = [
    "輪椅",
    "輪陪",
    "友善",
    "友陪",
    "陪同",
    "身障",
    "身心障礙",
]


def load_state():
    default = {
        "last_status": None,
        "last_general_seat_ids": [],
    }

    if not STATE_FILE.exists():
        return default

    try:
        data = json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        )
        default.update(data)
    except Exception:
        pass

    return default


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def send_line(message):
    token = os.environ.get(
        "LINE_CHANNEL_ACCESS_TOKEN",
        "",
    ).strip()

    if not token:
        raise RuntimeError(
            "找不到 LINE_CHANNEL_ACCESS_TOKEN"
        )

    payload = {
        "messages": [
            {
                "type": "text",
                "text": message,
            }
        ]
    }

    request = urllib.request.Request(
        "https://api.line.me/v2/bot/message/broadcast",
        data=json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=20,
    ) as response:
        response.read()

    print("📱 LINE 通知已送出")


def find_taipei_buy_button(page):
    for button_name in [
        "自行選位",
        "電腦配位",
    ]:
        locator = page.get_by_text(
            button_name,
            exact=True,
        )

        for i in range(locator.count()):
            candidate = locator.nth(i)

            if not candidate.is_visible():
                continue

            belongs_to_taipei = candidate.evaluate(
                """el => {
                    let node = el;

                    while (
                        node &&
                        node !== document.body
                    ) {
                        const text =
                            node.innerText || "";

                        if (
                            text.includes("2026/11/12") &&
                            text.includes("國家音樂廳")
                        ) {
                            return true;
                        }

                        node = node.parentElement;
                    }

                    return false;
                }"""
            )

            if belongs_to_taipei:
                return candidate

    return None


def extract_taipei_status(page):
    return page.evaluate(
        """() => {
            const candidates =
                [...document.querySelectorAll(
                    "body *"
                )].filter(el => {
                    const text =
                        el.innerText || "";

                    return (
                        text.includes("2026/11/12") &&
                        text.includes("國家音樂廳") &&
                        (
                            text.includes("完售") ||
                            text.includes("自行選位") ||
                            text.includes("電腦配位")
                        )
                    );
                });

            candidates.sort(
                (a, b) =>
                    (a.innerText || "").length -
                    (b.innerText || "").length
            );

            return candidates.length
                ? candidates[0].innerText
                : "";
        }"""
    )


def read_enabled_seats(page):
    return page.evaluate(
        """() => {

            function rgbKey(value) {
                if (!value) return "";

                const match = value.match(
                    /rgba?\\(\\s*(\\d+)\\s*,\\s*(\\d+)\\s*,\\s*(\\d+)/
                );

                if (!match) {
                    return value
                        .trim()
                        .toLowerCase();
                }

                return (
                    `rgb(${match[1]}, ${match[2]}, ${match[3]})`
                );
            }


            // 建立「顏色 → 票價」對照表
            const priceByColor = {};

            for (
                const row
                of document.querySelectorAll(
                    ".section-wrapper"
                )
            ) {
                const swatch =
                    row.querySelector(
                        ".circle--status"
                    );

                if (!swatch) {
                    continue;
                }

                const text =
                    (row.innerText || "")
                        .replace(/\\s+/g, " ")
                        .trim();

                const priceMatch =
                    text.match(
                        /[＄$]\\s*([\\d,]+)/
                    );

                if (!priceMatch) {
                    continue;
                }

                const price =
                    parseInt(
                        priceMatch[1]
                            .replace(/,/g, ""),
                        10
                    );

                const color =
                    rgbKey(
                        getComputedStyle(
                            swatch
                        ).backgroundColor
                    );

                if (!color) {
                    continue;
                }

                priceByColor[color] = {
                    price,
                    label: text,
                };
            }


            // 只找現在真的可以選的座位
            const seats = [];

            for (
                const seat
                of document.querySelectorAll(
                    'circle.seat[enabled="true"]'
                )
            ) {
                const id =
                    seat.getAttribute(
                        "id"
                    ) || "";

                const fill =
                    rgbKey(
                        getComputedStyle(
                            seat
                        ).fill ||
                        seat.style.fill ||
                        seat.getAttribute(
                            "fill"
                        ) ||
                        ""
                    );

                const legend =
                    priceByColor[
                        fill
                    ] || null;

                seats.push({
                    id,
                    fill,
                    price:
                        legend
                            ? legend.price
                            : null,
                    legend:
                        legend
                            ? legend.label
                            : "",
                });
            }

            return {
                priceByColor,
                seats,
            };
        }"""
    )


def is_excluded_seat(seat_id):
    return any(
        word in seat_id
        for word in EXCLUDED_WORDS
    )


def summarize_prices(general_seats):
    counts = {}

    for seat in general_seats:
        price = seat.get(
            "price"
        )

        key = (
            str(price)
            if price is not None
            else "unknown"
        )

        counts[key] = (
            counts.get(
                key,
                0,
            ) + 1
        )

    return counts


def line_message(general_seats):
    price_counts = (
        summarize_prices(
            general_seats
        )
    )

    known_prices = sorted(
        [
            int(price)
            for price
            in price_counts
            if price != "unknown"
        ],
        reverse=True,
    )

    lines = [
        "🚨🐕 汪汪汪！阿格麗希獵犬聞到票的味道了！",
        "",
        "瑪莎．阿格麗希｜2026 藝文饗宴",
        "📍 台北・國家音樂廳",
        "11/12（四）19:30",
        "",
    ]

    for price in known_prices:
        lines.append(
            f"🎟️ {price}"
            f"｜{price_counts[str(price)]} 張"
        )

    unknown_count = (
        price_counts.get(
            "unknown",
            0,
        )
    )

    if unknown_count:
        lines.append(
            "🎟️ 票價待確認"
            f"｜{unknown_count} 張"
        )

    lines.extend([
        "",
        f"一般可購買座位：{len(general_seats)} 張",
        "",
        "快去 OPENTIX 搶票！",
        URL,
    ])

    return "\n".join(
        lines
    )


def check_tickets():
    now_text = datetime.now(
        ZoneInfo(
            "Asia/Taipei"
        )
    ).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print(
        "🐕 雲端阿格麗希退票獵犬開始巡邏"
    )

    print(
        "檢查時間：",
        now_text,
    )

    print(
        "目標：2026/11/12 台北國家音樂廳"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True
        )

        context = browser.new_context(
            locale="zh-TW",
            viewport={
                "width": 1440,
                "height": 1200,
            },
        )

        page = context.new_page()

        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(
            5000
        )

        buy_button = (
            find_taipei_buy_button(
                page
            )
        )

        taipei_status = (
            extract_taipei_status(
                page
            )
        )

        if buy_button is None:
            browser.close()

            if (
                "完售"
                in taipei_status
            ):
                print(
                    "🥺🐕 台北場目前仍然完售。"
                )

                return (
                    "sold_out",
                    [],
                    [],
                )

            print(
                "⚠️ 台北場狀態無法判斷。"
            )

            return (
                "unknown",
                [],
                [],
            )

        print(
            "👃 找到台北場購票入口，"
            "正在檢查可選座位……"
        )

        old_page_count = len(
            context.pages
        )

        buy_button.click()

        page.wait_for_timeout(
            5000
        )

        if (
            len(context.pages)
            > old_page_count
        ):
            page = context.pages[-1]

        page.wait_for_timeout(
            5000
        )

        seat_data = (
            read_enabled_seats(
                page
            )
        )

        enabled_seats = (
            seat_data[
                "seats"
            ]
        )

        general_seats = []
        excluded_seats = []

        for seat in enabled_seats:
            if is_excluded_seat(
                seat["id"]
            ):
                excluded_seats.append(
                    seat
                )
            else:
                general_seats.append(
                    seat
                )

        print("")
        print(
            "========== 🐕 座位結果 =========="
        )

        print(
            "目前可選座位總數：",
            len(
                enabled_seats
            ),
        )

        print(
            "排除友善／輪椅相關：",
            len(
                excluded_seats
            ),
        )

        print(
            "一般可購買座位：",
            len(
                general_seats
            ),
        )

        if excluded_seats:
            print("")
            print(
                "🤐 已排除的座位："
            )

            for seat in (
                excluded_seats
            ):
                print(
                    "  ",
                    seat["id"],
                    "|",
                    seat["price"]
                    if seat[
                        "price"
                    ] is not None
                    else "票價未辨認",
                )

        if general_seats:
            print("")
            print(
                "🚨 一般可購買座位："
            )

            for seat in (
                general_seats
            ):
                print(
                    "  ",
                    seat["id"],
                    "|",
                    seat["price"]
                    if seat[
                        "price"
                    ] is not None
                    else "票價未辨認",
                )

        print(
            "================================"
        )

        print("")

        browser.close()

        if general_seats:
            return (
                "general",
                general_seats,
                excluded_seats,
            )

        if excluded_seats:
            return (
                "excluded_only",
                [],
                excluded_seats,
            )

        return (
            "unclear_available",
            [],
            [],
        )


def main():
    # 之後如果要看 LINE 版型，
    # 可以手動用這個模式測試，
    # 不需要真的等到退票。
    if "--test-line" in sys.argv:
        send_line(
            "\n".join([
                "🚨🐕 汪汪汪！阿格麗希獵犬聞到票的味道了！",
                "",
                "瑪莎．阿格麗希｜2026 藝文饗宴",
                "📍 台北・國家音樂廳",
                "11/12（四）19:30",
                "",
                "🎟️ 5800｜2 張",
                "🎟️ 4800｜1 張",
                "",
                "一般可購買座位：3 張",
                "",
                "快去 OPENTIX 搶票！",
            ])
        )

        return

    state = load_state()

    (
        status,
        general_seats,
        excluded_seats,
    ) = check_tickets()

    # 雖然 LINE 不顯示座號，
    # 但程式仍記住真正的座位 ID。
    # 如果同價位「一張消失、一張新出現」，
    # 即使張數沒變，也能重新通知你。
    current_general_ids = sorted(
        seat["id"]
        for seat
        in general_seats
    )

    previous_general_ids = sorted(
        state.get(
            "last_general_seat_ids",
            [],
        )
    )

    general_changed = (
        current_general_ids
        != previous_general_ids
    )

    if status == "general":

        if general_changed:
            send_line(
                line_message(
                    general_seats
                )
            )

        else:
            print(
                "🐕 同一批一般票仍在，"
                "這輪不重複 LINE 通知。"
            )

    elif (
        status
        == "excluded_only"
    ):
        print(
            "🤫 目前只有友善／輪椅相關座位，"
            "LINE 保持安靜。"
        )

    elif (
        status
        == "sold_out"
    ):
        print(
            "🤫 台北場完售，"
            "LINE 保持安靜。"
        )

    else:
        print(
            "⚠️ 有購票入口，"
            "但沒有辨認到可選座位。"
        )

        print(
            "為避免誤報，"
            "這輪先不傳 LINE。"
        )

    state[
        "last_status"
    ] = status

    state[
        "last_general_seat_ids"
    ] = current_general_ids

    save_state(
        state
    )


if __name__ == "__main__":
    main()
