import argparse
import sys
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table

from .gateway import StudiePlusGateway
from .config import Config, DEFAULT_PROFILE_DIR, DEFAULT_SCHEDULE_URL
from .parser import AuthenticationRequiredError

console = Console()


def print_day_table(day_schedule, console: Console):
    title = f"Schedule for {day_schedule.day_name or ''} {day_schedule.date}".strip()
    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("Time", style="yellow", no_wrap=True)
    table.add_column("Subject", style="bold green")
    table.add_column("Room", style="magenta")
    table.add_column("Teacher", style="blue")
    table.add_column("Group", style="dim")
    table.add_column("Homework / Notes", style="white")

    if not day_schedule.lessons:
        console.print(f"[yellow]No lessons found for {day_schedule.date}.[/yellow]")
        return

    for lesson in day_schedule.lessons:
        hw_note = []
        if lesson.homework:
            hw_note.append(f"[bold yellow]HW:[/bold yellow] {lesson.homework}")
        if lesson.note:
            hw_note.append(f"[dim]Note:[/dim] {lesson.note}")

        teacher_display = lesson.teacher or "-"
        if lesson.teacher and lesson.teacher_name and lesson.teacher_name != lesson.teacher:
            teacher_display = f"{lesson.teacher_name} ({lesson.teacher})"

        table.add_row(
            lesson.time or "-",
            lesson.subject,
            lesson.room or "-",
            teacher_display,
            lesson.group or "-",
            "\n".join(hw_note) if hw_note else "-"
        )

    console.print(table)


def print_conversations_table(conversations, show_content: bool = True):
    table = Table(title="Studie+ Conversations & Announcements", show_header=True, header_style="bold cyan")
    table.add_column("Date", style="yellow", no_wrap=True)
    table.add_column("Sender", style="bold green")
    table.add_column("Subject", style="white")
    table.add_column("Type", style="magenta")
    table.add_column("Attachments", style="cyan")

    if show_content:
        table.add_column("Content & Replies", style="dim")

    if not conversations:
        console.print("[yellow]No conversations found.[/yellow]")
        return

    for c in conversations:
        type_str = "[bold magenta]Announcement[/bold magenta]" if c.is_announcement else "Conversation"
        files_str = "\n".join(f"📄 {f}" for f in c.files) if c.files else "-"
        
        row_data = [
            c.date,
            c.sender,
            c.subject,
            type_str,
            files_str,
        ]

        if show_content:
            content_parts = []
            if c.content:
                content_parts.append(c.content)
            elif c.preview:
                content_parts.append(f"[dim]{c.preview}[/dim]")
            if c.comments:
                content_parts.append("\n[bold]Replies:[/bold]")
                for cm in c.comments:
                    content_parts.append(f"  [green]{cm.author}[/green]: {cm.content}")
            row_data.append("\n".join(content_parts) if content_parts else "-")

        table.add_row(*row_data)

    console.print(table)


def print_assignments_table(assignments, show_details: bool = False):
    table = Table(title="Studie+ Assignments", show_header=True, header_style="bold magenta")
    table.add_column("Due Date", style="yellow", no_wrap=True)
    table.add_column("Subject", style="bold green")
    table.add_column("Title", style="white")
    table.add_column("Status / Grade", style="cyan")
    table.add_column("Hours (P/B)", style="dim")

    if show_details:
        table.add_column("Description", style="white")
        table.add_column("Attached Files", style="bold blue")

    if not assignments:
        console.print("[yellow]No assignments found matching the criteria.[/yellow]")
        return

    for a in assignments:
        status_display = a.status.upper()
        if a.grade:
            status_display = f"[bold green]{a.grade}[/bold green]"
        elif a.status == "submitted":
            status_display = "[cyan]Submitted[/cyan]"
        elif a.status == "open":
            status_display = "[bold yellow]Open[/bold yellow]"

        hours = f"{a.student_time_allocated or '-'}/{a.student_time_used or '-'}"

        row_data = [
            a.due_date or "-",
            a.subject,
            a.title,
            status_display,
            hours,
        ]

        if show_details:
            desc_text = a.description or "[dim]No description[/dim]"
            files_text = "\n".join(f"📄 {f}" for f in a.files) if a.files else "[dim]No files[/dim]"
            row_data.extend([desc_text, files_text])

        table.add_row(*row_data)

    console.print(table)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studieplus",
        description="Studie+ (UDData+) Gateway: Schedule, Lessons & Assignments"
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
        help="Path to Firefox profile directory (default: ~/.mozilla/firefox/schedule.special)"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    login_parser = subparsers.add_parser("login", help="Interactive login with MitID in visible Firefox")
    login_parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds (default: 300)")

    subparsers.add_parser("status", help="Check if current profile session is authenticated")

    day_parser = subparsers.add_parser("day", help="Query lessons for a specific day (default: today)")
    day_parser.add_argument("date", nargs="?", default="today", help="Date: 'today', 'tomorrow', or 'YYYY-MM-DD'")
    day_parser.add_argument("--json", action="store_true", help="Output JSON")

    week_parser = subparsers.add_parser("week", help="Query lessons for the entire week")
    week_parser.add_argument("date", nargs="?", default="today", help="Date within the target week (default: today)")
    week_parser.add_argument("--json", action="store_true", help="Output JSON")

    as_parser = subparsers.add_parser("assignments", help="Query assignments, due dates, descriptions, files & grades")
    as_parser.add_argument("--status", choices=["open", "graded", "submitted", "all"], default="open", help="Filter by status (default: open)")
    as_parser.add_argument("--due", type=str, help="Specific due date ('today', 'tomorrow', or 'YYYY-MM-DD')")
    as_parser.add_argument("--from", dest="from_date", type=str, help="Due date on or after this date ('YYYY-MM-DD')")
    as_parser.add_argument("--to", dest="to_date", type=str, help="Due date on or before this date ('YYYY-MM-DD')")
    as_parser.add_argument("--days", type=int, help="Due within the next N days")
    as_parser.add_argument("--subject", type=str, help="Filter by subject (e.g. Maths, TOK, His)")
    as_parser.add_argument("-d", "--details", action="store_true", help="Fetch description and attached file names")
    as_parser.add_argument("--download", type=Path, help="Download attached files into the given directory")
    as_parser.add_argument("--json", action="store_true", help="Output JSON")

    conv_parser = subparsers.add_parser("conversations", aliases=["messages"], help="Query conversations and announcements")
    conv_parser.add_argument("--limit", type=int, default=10, help="Number of conversations to retrieve (default: 10)")
    conv_parser.add_argument("--no-content", action="store_true", help="Do not fetch full message content/thread")
    conv_parser.add_argument("--all", action="store_true", help="View all conversations instead of only last 14 days")
    conv_parser.add_argument("--json", action="store_true", help="Output JSON")

    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    config = Config(profile_dir=args.profile)
    gateway = StudiePlusGateway(config=config)

    if args.command == "login":
        success = gateway.login(timeout=args.timeout)
        sys.exit(0 if success else 1)

    elif args.command == "status":
        console.print("[dim]Checking session headlessly...[/dim]")
        logged_in = gateway.is_logged_in()
        if logged_in:
            console.print("[bold green]✓ Session is active and authenticated![/bold green]")
        else:
            console.print("[bold yellow]! Session is not authenticated or expired.[/bold yellow]")
            console.print("Run [bold cyan]studieplus login[/bold cyan] to log in with MitID.")

    elif args.command == "day":
        try:
            day_schedule = gateway.get_day(args.date)
            if args.json:
                print(day_schedule.model_dump_json(indent=2))
            else:
                print_day_table(day_schedule, console)
        except AuthenticationRequiredError as e:
            console.print(f"[bold red]Authentication Error:[/bold red] {e}")
            sys.exit(1)

    elif args.command == "week":
        try:
            week = gateway.get_week(args.date)
            if args.json:
                print(week.model_dump_json(indent=2))
            else:
                if week.week_info:
                    console.print(f"[bold cyan]=== {week.week_info} ===[/bold cyan]\n")
                for day in week.days:
                    print_day_table(day, console)
                    console.print()
        except AuthenticationRequiredError as e:
            console.print(f"[bold red]Authentication Error:[/bold red] {e}")
            sys.exit(1)

    elif args.command == "assignments":
        try:
            with_details = args.details or bool(args.download)
            assignments = gateway.get_assignments(
                status=args.status,
                due_date=args.due,
                from_date=args.from_date,
                to_date=args.to_date,
                days_ahead=args.days,
                subject=args.subject,
                with_details=with_details,
                download_dir=args.download,
            )
            if args.json:
                print(json.dumps([a.model_dump() for a in assignments], indent=2))
            else:
                print_assignments_table(assignments, show_details=with_details)
        except AuthenticationRequiredError as e:
            console.print(f"[bold red]Authentication Error:[/bold red] {e}")
            sys.exit(1)

    elif args.command in ("conversations", "messages"):
        try:
            with_content = not args.no_content
            convs = gateway.get_conversations(
                limit=args.limit,
                with_content=with_content,
                view_all=args.all,
            )
            if args.json:
                print(json.dumps([c.model_dump() for c in convs], indent=2, ensure_ascii=False))
            else:
                print_conversations_table(convs, show_content=with_content)
        except AuthenticationRequiredError as e:
            console.print(f"[bold red]Authentication Error:[/bold red] {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
