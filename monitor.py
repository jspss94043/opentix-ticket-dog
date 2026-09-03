from datetime import datetime
from pathlib import Path
import json
import re
import time
import urllib.request

from playwright.sync_api import sync_playwright


URL = "https://www.opentix.life/event/2076925048527581185"

TOPIC_FILE = Path(".ntfy_topic")
STATE_FILE = Path("dog_state.json")
LOG_FILE = Path("ticket_history.log")

HEARTBEAT_SECONDS = 3600

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
        "last_heartbeat": 0,
        "last_inventory": {},
        "last_status": None,
        "alert_active": False,
    }

    if not STATE_FILE.exists():
        return default

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        default.update(data)
    except Exception:
        pass

    return default


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def send_ntfy(title, message, priority=3):
    if not TOPIC_FILE.exists():
        print("⚠️ 找不到 .ntfy_topic")
        return False

    topic = TOPIC_FILE.read_text(encoding="utf-8").strip()

    payload = {
        "topic": topic,
        "title": title,
        "message": message,
        "priority": priority,
        "click": URL,
    }

    try:
        request = urllib.request.Request(
            "https://ntfy.sh",
            data=json.dumps(
                payload,
                ensure_ascii=False
            ).encode("utf-8"),
            headers={
                "Content-Type": "application/json"
            },
        )

        with urllib.request.urlopen(request, timeout=15):
            pass

        return True

    except Exception as error:
        print("⚠️ 手機通知傳送失敗：", error)
        return False


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
            line
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


def inventory_message(tickets):
    lines = [
        "台北場｜11/12 19:30｜國家音樂廳"
    ]

    for name, remaining in tickets:
        lines.append(
            f"🎟️ {name}｜剩 {remaining} 張"
        )

    lines.append("")
    lines.append("快去 OPENTIX 搶票！")

    return "\n".join(lines)


def write_history(status, tickets=None):
    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    with LOG_FILE.open(
        "a",
        encoding="utf-8"
    ) as file:

        file.write(
            f"\n[{now}] {status}\n"
        )

        if tickets:
            for name, remaining in tickets:
                file.write(
                    f"  {name}｜剩 {remaining}\n"
                )


state = load_state()

now = datetime.now()
now_text = now.strftime("%Y-%m-%d %H:%M:%S")
now_timestamp = time.time()

print("🐕 阿格麗希退票獵犬開始工作")
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
        "電腦配位"
    ]:
        locator = page.get_by_text(
            button_name,
            exact=True
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
            page.locator(
                "body"
            ).inner_text()
        )

        Path(
            "argerich_ticket_page.txt"
        ).write_text(
            ticket_text,
            encoding="utf-8"
        )

        (
            normal_tickets,
            excluded_tickets
        ) = parse_ticket_inventory(
            ticket_text
        )


        if normal_tickets:
            status = "general"

            print("")
            print(
                "🚨🐕 汪汪汪！"
                "阿格麗希獵犬聞到票的味道了！"
            )

            for (
                name,
                remaining
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
                "🐕 獵犬沒有吵主人。"
            )

        else:
            status = "unknown"

            print(
                "⚠️ 有購票入口，"
                "但暫時無法辨認票種。"
            )


    browser.close()


current_inventory = inventory_dict(
    normal_tickets
)

inventory_changed = (
    current_inventory
    != state["last_inventory"]
)

status_changed = (
    status
    != state["last_status"]
)


# 票況有變化就寫進日誌
if inventory_changed or status_changed:

    if status == "general":
        write_history(
            "一般票釋出",
            normal_tickets
        )

    elif status == "excluded_only":
        write_history(
            "只有友善／輪椅相關座位"
        )

    elif status == "sold_out":
        write_history(
            "完售／無一般票"
        )

    else:
        write_history(
            "頁面狀態無法判斷"
        )


# 第一次聞到這一批一般票：緊急爆叫
if status == "general":

    if not state["alert_active"]:

        send_ntfy(
            "🚨🐕 汪汪汪！"
            "阿格麗希獵犬聞到票的味道了！",
            inventory_message(
                normal_tickets
            ),
            priority=5,
        )

        state["alert_active"] = True

    # 同一批票還在，但張數有變化：
    # 留一則普通通知作為票況紀錄
    elif inventory_changed:

        send_ntfy(
            "🐕📋 阿格麗希票況更新",
            inventory_message(
                normal_tickets
            ),
            priority=3,
        )


# 一般票消失後，重新解除警戒
else:
    state["alert_active"] = False


# 沒有一般票時，每 10 分鐘在 ntfy 靜默留一筆巡邏紀錄
if status != "general":

    if status == "sold_out":
        silent_message = (
            f"🥺🐕 台北場目前仍然完售。\n"
            f"巡邏時間：{now_text}"
        )

    elif status == "excluded_only":
        silent_message = (
            f"🥺🐕 這輪只有友善／輪椅相關座位，沒有一般票。\n"
            f"巡邏時間：{now_text}"
        )

    else:
        silent_message = (
            f"🥺🐕 這輪巡邏無法確認票況。\n"
            f"巡邏時間：{now_text}"
        )

    send_ntfy(
        "🥺🐕 阿格麗希獵犬這輪沒有聞到票",
        silent_message,
        priority=1,
    )


# 沒有一般票時，每小時報一次平安
if status != "general":

    if (
        now_timestamp
        - state["last_heartbeat"]
        >= HEARTBEAT_SECONDS
    ):

        heartbeat = (
            f"最近巡邏：{now_text}"
        )

        sent = send_ntfy(
            "👀🐕 阿格麗希獵犬沒有偷懶，"
            "還醒著盯票！",
            heartbeat,
            priority=3,
        )

        if sent:
            state["last_heartbeat"] = (
                now_timestamp
            )


state["last_inventory"] = (
    current_inventory
)

state["last_status"] = status

save_state(state)
