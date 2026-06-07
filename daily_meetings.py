from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
import os

from otterai import OtterAI

SCRIPT_DIR = Path(__file__).resolve().parent


def get_meeting_date():
    explicit = os.getenv("MEETING_DATE")
    if explicit:
        return datetime.strptime(explicit, "%Y-%m-%d").date()
    offset = int(os.getenv("MEETING_DATE_OFFSET", "0"))
    return datetime.now().date() - timedelta(days=offset)


def get_output_path(meeting_date):
    output_dir = os.getenv("OBSIDIAN_MEETINGS_DIR")
    base = Path(output_dir).expanduser() if output_dir else Path.cwd()
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{meeting_date.isoformat()}.md"




def parse_outline(speech):
    outline = []
    for section in speech.get("speech_outline") or []:
        points = [
            segment["text"]
            for segment in section.get("segments") or []
            if segment.get("text")
        ]
        if section.get("text") or points:
            outline.append({"section": section.get("text"), "points": points})
    return outline


def parse_meeting(speech, otter):
    action_items = otter.get_action_items(speech["otid"])["data"].get("speech_action_items", [])
    return {
        "title": speech.get("title", "Untitled meeting"),
        "start_time": speech["start_time"],
        "end_time": speech.get("end_time"),
        "summary": speech.get("summary") or "",
        "speakers": [
            speaker["speaker_name"]
            for speaker in speech.get("speakers") or []
            if speaker.get("speaker_name")
        ],
        "outline": parse_outline(speech),
        "action_items": [
            {
                "text": item.get("text", ""),
                "assignee": (item.get("assignee") or {}).get("name"),
                "completed": item.get("completed", False),
            }
            for item in action_items
            if item.get("text")
        ],
    }


def format_datetime(timestamp):
    if not timestamp:
        return "Unknown"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %I:%M %p")


def format_time(timestamp):
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%I:%M %p")


def format_frontmatter(meeting_date, meeting_count):
    tags = [
        tag.strip()
        for tag in os.getenv("OBSIDIAN_TAGS", "otter,meetings").split(",")
        if tag.strip()
    ]
    tag_lines = "\n".join(f"  - {tag}" for tag in tags)
    return "\n".join(
        [
            "---",
            f"date: {meeting_date.isoformat()}",
            "tags:",
            tag_lines,
            "source: otter.ai",
            f"meetings: {meeting_count}",
            "---",
        ]
    )


def format_meeting_toc(meetings):
    lines = ["## Meetings", ""]
    for meeting in meetings:
        time_label = format_time(meeting["start_time"])
        link_label = f"{meeting['title']} ({time_label})" if time_label else meeting["title"]
        lines.append(f"- [[#{meeting['title']}|{link_label}]]")
    lines.append("")
    return lines


def format_meeting_report(meeting):
    when = format_datetime(meeting["start_time"])
    if meeting.get("end_time"):
        when += f" – {format_time(meeting['end_time'])}"

    lines = [
        f"## {meeting['title']}",
        "",
        f"**When:** {when}  ",
        f"**Speakers:** {', '.join(meeting['speakers']) or 'None listed'}",
        "",
    ]

    summary = meeting["summary"] or "_No summary available._"
    lines.extend(
        [
            "> [!abstract] Summary",
            f"> {summary.replace(chr(10), chr(10) + '> ')}",
            "",
            "### Outline",
        ]
    )

    if meeting["outline"]:
        for section in meeting["outline"]:
            if section["section"]:
                lines.append(f"#### {section['section']}")
            for point in section["points"]:
                lines.append(f"- {point}")
            lines.append("")
    else:
        lines.append("_No outline available._")
        lines.append("")

    lines.append("### Action Items")
    if meeting["action_items"]:
        for item in meeting["action_items"]:
            checkbox = "[x]" if item["completed"] else "[ ]"
            assignee = f" ({item['assignee']})" if item["assignee"] else ""
            lines.append(f"- {checkbox} {item['text']}{assignee}")
    else:
        lines.append("_No action items found._")

    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def main():
    load_dotenv()
    meeting_date = get_meeting_date()

    otter = OtterAI()
    login = otter.login(
        os.getenv("OTTER_USERNAME"), os.getenv("OTTER_PASSWORD")
    )
    if login["status"] != 200:
        raise RuntimeError(f"Login failed: {login}")

    speeches_response = otter.get_speeches(page_size=45)
    if speeches_response["status"] != 200:
        raise RuntimeError(f"Failed to fetch speeches: {speeches_response}")

    todays_speeches = [
        speech
        for speech in speeches_response["data"]["speeches"]
        if datetime.fromtimestamp(speech["start_time"]).date() == meeting_date
    ]

    meetings = [parse_meeting(speech, otter) for speech in todays_speeches]
    meetings.sort(key=lambda meeting: meeting["start_time"])

    report_parts = [
        format_frontmatter(meeting_date, len(meetings)),
        "",
        f"# Daily Meetings – {meeting_date.isoformat()}",
        "",
    ]

    if meetings:
        report_parts.extend(format_meeting_toc(meetings))
        for meeting in meetings:
            report_parts.append(format_meeting_report(meeting))
    else:
        report_parts.extend(
            [
                "> [!info] No meetings",
                f"> No Otter meetings were found for {meeting_date.isoformat()}.",
                "",
            ]
        )

    output_path = get_output_path(meeting_date)
    output_path.write_text("\n".join(report_parts), encoding="utf-8")
    print(f"Wrote {len(meetings)} meeting(s) to {output_path}")


if __name__ == "__main__":
    main()
