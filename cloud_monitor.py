from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import re
import sys
import urllib.request

from playwright.sync_api import sync_playwright


URL = "https://www.opentix.life/event/2076925048527581185"
STATE_FILE = Path("cloud_state.json")

EXCLUDED_WORDS = [
    "輪椅",
    "輪椅陪同席",
    "多元友善",
    "陪同席",
    "身障",
    "身心障礙",
]


def load_state():
    default = {
        "last_status": None,
        "last_inventory": {},
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


def parse_ticket_inventory(text):
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    normal_tickets = []
    excluded_tickets = []

    for i, line in enumerate(lines):
        match = re.fullmatch(
            r"剩\s*[:：]\s*(\d+)",
            line,
        )

        if not match or i == 0:
            continue

        remaining = int(match.group(1))

        if remaining <= 0:
            continue

        ticket_name = lines[i - 1]

        if any(
            word in ticket_name
            for word in EXCLUDED_WORDS
        ):
            excluded_tickets.append(
                (ticket_name, remaining)
            )
        else:
            normal_tickets.append(
                (ticket_name, remaining)
            )

    return normal_tickets, excluded_tickets


def inventory_dict(tickets):
    return {
        name: remaining
        for name, remaining in tickets
    }


def ticket_message(tickets):
    lines = [
        "🚨🐕 汪汪汪！阿格麗希獵犬聞到票的味道了！",
        "",
        "🎹 2026 瑪莎．阿格麗希",
        "📍 台北｜國家音樂廳",
        "🕢 2026/11/12 19:30",
        "",
    ]

    for name, remaining in tickets:
        lines.append(
            f"🎟️ {name}｜剩 {remaining} 張"
        )

    lines.extend([
        "",
        "快去 OPENTIX 搶票！",
        URL,
    ])

    return "\n".join(lines)


def unclear_message():
    return "\n".join([
        "⚠️🐕 阿格麗希獵犬發現台北場有購票入口，",
        "但 OPENTIX 目前無法清楚辨認票種。",
        "",
        "可能有可購買座位，建議立刻進 OPENTIX 看看。",
        URL,
    ])


def check_tickets():
    now_text = datetime.now(
        ZoneInfo("Asia/Taipei")
    ).strftime("%Y-%m-%d %H:%M:%S")

    print("🐕 雲端阿格麗希退票獵犬開始巡邏")
    print("檢查時間：", now_text)
    print("目標：2026/11/12 台北國家音樂廳")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True
        )

        context = browser.new_context(
            locale="zh-TW"
        )

        page = context.new_page()

        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(5000)

        buy_button = None

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

                belongs_to_taipei = (
                    candidate.evaluate(
                        """el => {
                            let node = el;

                            while (
                                node &&
                                node !== document.body
                            ) {
                                const text =
                                    node.innerText || "";

                                if (
                                    text.includes(
                                        "2026/11/12"
                                    ) &&
                                    text.includes(
                                        "國家音樂廳"
                                    )
                                ) {
                                    return true;
                                }

                                node =
                                    node.parentElement;
                            }

                            return false;
                        }"""
                    )
                )

                if belongs_to_taipei:
                    buy_button = candidate
                    break

            if buy_button is not None:
                break

        taipei_status = page.evaluate(
            """() => {
                const candidates =
                    [...document.querySelectorAll(
                        "body *"
                    )].filter(el => {
                        const text =
                            el.innerText || "";

                        return (
                            text.includes(
                                "2026/11/12"
                            ) &&
                            text.includes(
                                "國家音樂廳"
                            ) &&
                            (
                                text.includes(
                                    "完售"
                                ) ||
                                text.includes(
                                    "自行選位"
                                ) ||
                                text.includes(
                                    "電腦配位"
                                )
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

        normal_tickets = []
        excluded_tickets = []
        status = "unknown"

        if buy_button is None:

            if "完售" in taipei_status:
                status = "sold_out"

                print(
                    "🥺🐕 台北場目前仍然完售。"
                )

            else:
                status = "unknown"

                print(
                    "⚠️ 台北場狀態無法判斷。"
                )

        else:
            print(
                "👃 獵犬發現台北場購票入口，"
                "正在聞票……"
            )

            old_page_count = len(
                context.pages
            )

            buy_button.click()

            page.wait_for_timeout(5000)

            if (
                len(context.pages)
                > old_page_count
            ):
                page = context.pages[-1]

            page.wait_for_timeout(3000)

            ticket_text = (
                page.locator("body").inner_text()
            )

            (
                normal_tickets,
                excluded_tickets,
            ) = parse_ticket_inventory(
                ticket_text
            )

            if normal_tickets:
                status = "general"

                print("")
                print(
                    "🚨🐕 發現一般票！"
                )

                for (
                    name,
                    remaining,
                ) in normal_tickets:
                    print(
                        f"🎟️ {name}"
                        f"｜剩 {remaining}"
                    )

            elif excluded_tickets:
                status = "excluded_only"

                print(
                    "🤐 目前只有友善／"
                    "輪椅相關座位。"
                )

                print(
                    "🐕 LINE 保持安靜。"
                )

            else:
                status = "unclear_available"

                print(
                    "⚠️ 有購票入口，"
                    "但暫時無法辨認票種。"
                )

        browser.close()

    return status, normal_tickets


def main():
    if "--test-line" in sys.argv:
        send_line(
            "🐕✅ 演出退票獵犬 LINE 測試成功！\n"
            "雲端狗狗已經會透過 LINE 說話了。"
        )
        return

    state = load_state()

    (
        status,
        normal_tickets,
    ) = check_tickets()

    current_inventory = inventory_dict(
        normal_tickets
    )

    previous_status = state.get(
        "last_status"
    )

    previous_inventory = state.get(
        "last_inventory",
        {},
    )

    inventory_changed = (
        current_inventory
        != previous_inventory
    )

    status_changed = (
        status
        != previous_status
    )

    if status == "general":

        if (
            status_changed
            or inventory_changed
        ):
            send_line(
                ticket_message(
                    normal_tickets
                )
            )

        else:
            print(
                "🐕 同一批一般票仍在，"
                "這輪不重複 LINE 通知。"
            )

    elif status == "unclear_available":

        if status_changed:
            send_line(
                unclear_message()
            )

        else:
            print(
                "🐕 購票入口狀態沒有變化，"
                "這輪不重複 LINE 通知。"
            )

    else:
        print(
            "🤫 這輪沒有一般票，"
            "LINE 保持安靜。"
        )

    state["last_status"] = status
    state["last_inventory"] = (
        current_inventory
    )

    save_state(state)


if __name__ == "__main__":
    main()
