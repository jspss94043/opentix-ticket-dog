from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json

from playwright.sync_api import sync_playwright


URL = "https://www.opentix.life/event/2076925048527581185"


def find_taipei_buy_button(page):
    """
    只找：
    2026/11/12
    國家音樂廳
    的自行選位／電腦配位按鈕。
    """

    for button_name in [
        "自行選位",
        "電腦配位",
    ]:
        locator = page.get_by_text(
            button_name,
            exact=True,
        )

        for i in range(
            locator.count()
        ):
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
                return candidate

    return None


def main():
    now_text = datetime.now(
        ZoneInfo("Asia/Taipei")
    ).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print(
        "🐕🔬 座位偵探狗開始工作"
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

        if buy_button is None:
            print(
                "🥺 沒有找到台北場購票入口。"
            )
            browser.close()
            return

        print(
            "👃 找到台北場購票入口，"
            "準備進入座位圖。"
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

        print(
            "目前頁面：",
            page.url,
        )

        # ---------------------------------
        # 1. 保存最原始的頁面資料
        # ---------------------------------

        body_text = (
            page.locator(
                "body"
            ).inner_text()
        )

        Path(
            "seat_probe_text.txt"
        ).write_text(
            body_text,
            encoding="utf-8",
        )

        Path(
            "seat_probe_page.html"
        ).write_text(
            page.content(),
            encoding="utf-8",
        )

        page.screenshot(
            path="seat_probe_page.png",
            full_page=True,
        )

        # ---------------------------------
        # 2. 深入檢查 DOM
        # ---------------------------------

        probe_result = page.evaluate(
            """() => {

                function attrsOf(el) {
                    const result = {};

                    for (
                        const attr
                        of [...el.attributes]
                    ) {
                        result[attr.name] =
                            attr.value;
                    }

                    return result;
                }


                function shortText(el) {
                    const value = (
                        el.innerText ||
                        el.textContent ||
                        ""
                    )
                        .replace(
                            /\\s+/g,
                            " "
                        )
                        .trim();

                    return value.slice(
                        0,
                        300
                    );
                }


                function rectOf(el) {
                    const r =
                        el.getBoundingClientRect();

                    return {
                        x:
                            Math.round(r.x),
                        y:
                            Math.round(r.y),
                        width:
                            Math.round(r.width),
                        height:
                            Math.round(r.height),
                    };
                }


                function parentChain(el) {
                    const chain = [];

                    let node =
                        el.parentElement;

                    let level = 0;

                    while (
                        node &&
                        node !== document.body &&
                        level < 5
                    ) {
                        chain.push({
                            level:
                                level + 1,
                            tag:
                                node.tagName,
                            id:
                                node.id || "",
                            className:
                                typeof node.className
                                === "string"
                                    ? node.className
                                    : "",
                            text:
                                shortText(
                                    node
                                ).slice(
                                    0,
                                    200
                                ),
                            attributes:
                                attrsOf(
                                    node
                                ),
                        });

                        node =
                            node.parentElement;

                        level += 1;
                    }

                    return chain;
                }


                const all = [
                    ...document.querySelectorAll(
                        "*"
                    )
                ];


                const seatWords =
                    /seat|chair|ticket|available|select|wheel|accessible|friendly|disabled|active|友善|友陪|輪椅|輪陪|座位|座席/i;


                const candidates = [];


                for (
                    const el
                    of all
                ) {
                    const tag =
                        el.tagName.toLowerCase();

                    const attributes =
                        attrsOf(el);

                    const text =
                        shortText(el);

                    const id =
                        el.id || "";

                    const className =
                        typeof el.className
                        === "string"
                            ? el.className
                            : "";

                    const attrText =
                        Object.entries(
                            attributes
                        )
                            .map(
                                ([key, value]) =>
                                    `${key}=${value}`
                            )
                            .join(" ");

                    const combined =
                        [
                            tag,
                            id,
                            className,
                            text,
                            attrText,
                        ].join(" ");

                    const style =
                        getComputedStyle(el);

                    const rect =
                        el.getBoundingClientRect();

                    const hasData =
                        Object.keys(
                            attributes
                        ).some(
                            key =>
                                key.startsWith(
                                    "data-"
                                )
                        );

                    const hasAria =
                        attributes[
                            "aria-label"
                        ] ||
                        attributes[
                            "aria-describedby"
                        ] ||
                        attributes[
                            "aria-labelledby"
                        ];

                    const specialTag =
                        [
                            "button",
                            "a",
                            "input",
                            "option",
                        ].includes(tag);

                    const svgInteractiveTag =
                        [
                            "g",
                            "use",
                            "circle",
                            "rect",
                            "path",
                            "polygon",
                            "text",
                        ].includes(tag);

                    const looksSeatLike =
                        seatWords.test(
                            combined
                        );

                    const looksInteractive =
                        style.cursor
                            === "pointer" ||
                        el.tabIndex >= 0 ||
                        "onclick"
                            in attributes ||
                        attributes[
                            "role"
                        ]
                            === "button";

                    const usefulSvg =
                        svgInteractiveTag &&
                        (
                            looksSeatLike ||
                            looksInteractive ||
                            hasData ||
                            hasAria
                        );

                    const interesting =
                        specialTag ||
                        usefulSvg ||
                        looksSeatLike ||
                        looksInteractive ||
                        hasData ||
                        hasAria;

                    if (!interesting) {
                        continue;
                    }

                    # 只記錄目前真正有尺寸的元素，
                    # 以及有重要座位文字的元素。
                    if (
                        rect.width <= 0 &&
                        rect.height <= 0 &&
                        !looksSeatLike
                    ) {
                        continue;
                    }

                    candidates.push({
                        tag,
                        id,
                        className,
                        text,
                        attributes,
                        cursor:
                            style.cursor,
                        display:
                            style.display,
                        visibility:
                            style.visibility,
                        opacity:
                            style.opacity,
                        pointerEvents:
                            style.pointerEvents,
                        tabIndex:
                            el.tabIndex,
                        disabled:
                            Boolean(
                                el.disabled
                            ),
                        rect:
                            rectOf(el),
                        parents:
                            parentChain(el),
                    });
                }


                # --------------------------
                # 專門尋找：
                # 輪椅席／輪陪席／友善席／友陪席
                # --------------------------

                const specialSeatWords = [
                    "輪椅席",
                    "輪陪席",
                    "輪椅陪同席",
                    "友善席",
                    "友陪席",
                    "多元友善席",
                    "多元友善陪同席",
                ];


                const specialLabels = [];


                for (
                    const el
                    of all
                ) {
                    const text =
                        shortText(el);

                    if (
                        !specialSeatWords.some(
                            word =>
                                text === word
                        )
                    ) {
                        continue;
                    }

                    specialLabels.push({
                        text,
                        tag:
                            el.tagName,
                        id:
                            el.id || "",
                        className:
                            typeof el.className
                            === "string"
                                ? el.className
                                : "",
                        attributes:
                            attrsOf(el),
                        rect:
                            rectOf(el),
                        parents:
                            parentChain(el),
                    });
                }


                # --------------------------
                # 看看是不是 Canvas 座位圖
                # --------------------------

                const canvases = [
                    ...document.querySelectorAll(
                        "canvas"
                    )
                ].map(
                    (el, index) => ({
                        index,
                        width:
                            el.width,
                        height:
                            el.height,
                        rect:
                            rectOf(el),
                        attributes:
                            attrsOf(el),
                        className:
                            typeof el.className
                            === "string"
                                ? el.className
                                : "",
                    })
                );


                # --------------------------
                # 看看是不是 SVG 座位圖
                # --------------------------

                const svgs = [
                    ...document.querySelectorAll(
                        "svg"
                    )
                ].map(
                    (el, index) => ({
                        index,
                        rect:
                            rectOf(el),
                        attributes:
                            attrsOf(el),
                        className:
                            typeof el.className
                            === "string"
                                ? el.className
                                : "",
                        childCount:
                            el.querySelectorAll(
                                "*"
                            ).length,
                    })
                );


                return {
                    url:
                        location.href,
                    title:
                        document.title,
                    totalElements:
                        all.length,
                    candidateCount:
                        candidates.length,
                    candidates:
                        candidates.slice(
                            0,
                            5000
                        ),
                    specialLabelCount:
                        specialLabels.length,
                    specialLabels,
                    canvasCount:
                        canvases.length,
                    canvases,
                    svgCount:
                        svgs.length,
                    svgs,
                };
            }"""
        )

        Path(
            "seat_probe_result.json"
        ).write_text(
            json.dumps(
                probe_result,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        # ---------------------------------
        # 3. GitHub log 顯示摘要
        # ---------------------------------

        print("")
        print(
            "========== 🐕🔬 座位偵測摘要 =========="
        )

        print(
            "網頁元素總數：",
            probe_result[
                "totalElements"
            ],
        )

        print(
            "疑似座位／可操作元素：",
            probe_result[
                "candidateCount"
            ],
        )

        print(
            "友善／輪椅文字標籤：",
            probe_result[
                "specialLabelCount"
            ],
        )

        print(
            "Canvas 數量：",
            probe_result[
                "canvasCount"
            ],
        )

        print(
            "SVG 數量：",
            probe_result[
                "svgCount"
            ],
        )

        print("")
        print(
            "特殊座位標籤："
        )

        for item in (
            probe_result[
                "specialLabels"
            ][:50]
        ):
            print(
                "💺",
                item["text"],
                "| tag:",
                item["tag"],
                "| class:",
                item[
                    "className"
                ],
                "| attrs:",
                item[
                    "attributes"
                ],
            )

        print(
            "======================================"
        )

        print("")
        print(
            "✅ 已產生："
        )
        print(
            "seat_probe_result.json"
        )
        print(
            "seat_probe_page.html"
        )
        print(
            "seat_probe_text.txt"
        )
        print(
            "seat_probe_page.png"
        )

        browser.close()


if __name__ == "__main__":
    main()
