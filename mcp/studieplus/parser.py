import html
import re
import time
from datetime import datetime, date
from typing import List, Optional, Dict, Any, Tuple
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .models import Lesson, DaySchedule, WeekSchedule, Assignment, Conversation, ConversationComment
from .teachers import resolve_teacher_name, get_initials_for_teacher
from .auth import is_authenticated_url


class AuthenticationRequiredError(Exception):
    """Raised when the session is not authenticated or expired."""
    pass


def parse_danish_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parses date/datetime strings like '06.10.2026 08:30' or '2026-10-06'."""
    if not dt_str:
        return None
    dt_str = dt_str.strip()
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            pass
    return None


class StudiePlusParser:
    """Parses schedule and assignments from Studie+ (uddataplus.dk)."""

    def __init__(self, driver):
        self.driver = driver

    def check_auth(self):
        if not is_authenticated_url(self.driver.current_url, self.driver.title):
            raise AuthenticationRequiredError(
                f"Session not authenticated. Current URL: {self.driver.current_url}. Run 'studieplus login' first."
            )

    def wait_for_schedule_render(self, timeout: int = 15) -> None:
        """Waits until the SVG timetable is rendered in the DOM."""
        self.check_auth()
        WebDriverWait(self.driver, timeout).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, "g.DagMedBrikker")) > 0
        )
        time.sleep(1)

    def parse_tile(self, tile, day_date: str, day_name: str) -> Lesson:
        """Parses a single SVG lesson tile into a Lesson model."""
        raw_texts = []
        for t in tile.find_all("text"):
            style = t.get("style", "")
            classes = t.get("class", [])
            if "FontAwesome" in style or any("CAHE1CD-v-j" in c for c in classes):
                continue
            txt = t.get_text(strip=True)
            if txt and ord(txt[0]) < 0xE000:
                raw_texts.append(txt)

        titles = [t.get_text(strip=True) for t in tile.find_all("title")]

        time_match = None
        time_str = None
        clean_texts = []
        for txt in raw_texts:
            m = re.search(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", txt)
            if m and not time_match:
                time_match = (m.group(1), m.group(2))
                time_str = f"{m.group(1)}-{m.group(2)}"
            else:
                clean_texts.append(txt)

        subject = clean_texts[0] if clean_texts else "Unknown"

        homework = None
        note = None
        for title in titles:
            if "*** Homework ***" in title:
                hw_part = title.split("*** Homework ***")[1]
                if "*** Notes ***" in hw_part:
                    hw_sub, note_sub = hw_part.split("*** Notes ***", 1)
                    homework = hw_sub.strip()
                    note = note_sub.strip()
                else:
                    homework = hw_part.strip()
            elif "*** Notes ***" in title and not note:
                note = title.split("*** Notes ***")[1].strip()
            elif any(kw in title.lower() for kw in ["not mandatory", "mandatory attendance", "present", "exemption", "registered"]):
                pass
            elif not note and title not in ["more actions", "Show education period"]:
                note = title

        room = None
        teacher = None
        group = None
        for txt in clean_texts[1:]:
            if txt.startswith("*") or "-IB" in txt or txt.startswith("25ibt"):
                group = txt
            elif re.match(r"^[A-Z]{1,2}\d{3}[a-z]?$", txt):
                room = txt
            elif len(txt) <= 12 and not room and re.search(r"\d", txt):
                room = txt
            elif len(txt) <= 10 and not teacher:
                teacher = txt

        teacher_name = resolve_teacher_name(teacher)

        return Lesson(
            date=day_date,
            day_name=day_name,
            time=time_str,
            start_time=time_match[0] if time_match else None,
            end_time=time_match[1] if time_match else None,
            subject=subject,
            room=room,
            teacher=teacher,
            teacher_name=teacher_name,
            group=group,
            homework=homework,
            note=note,
            is_cancelled="aflyst" in subject.lower(),
        )

    def parse_schedule(self, target_date_hint: Optional[str] = None) -> WeekSchedule:
        """Parses the current rendered schedule into a WeekSchedule."""
        self.wait_for_schedule_render()
        soup = BeautifulSoup(self.driver.page_source, "html.parser")

        current_year = datetime.now().year
        header_text = soup.get_text()
        year_match = re.search(r"Week\s+\d+\s*-\s*(\d{4})", header_text, re.IGNORECASE)
        if year_match:
            current_year = int(year_match.group(1))
        elif target_date_hint and re.match(r"^\d{4}", target_date_hint):
            current_year = int(target_date_hint[:4])

        labels = [l.get_text(strip=True) for l in soup.find_all("div", class_="gwt-Label")]
        raw_days = [l for l in labels if re.search(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Man|Tir|Ons|Tor|Fre|Lør|Søn)\s+\d+/\d+", l)]

        dage = soup.find_all("g", class_="DagMedBrikker")
        week_days: List[DaySchedule] = []

        for i, dag in enumerate(dage):
            day_label = raw_days[i] if i < len(raw_days) else f"Day {i}"
            date_str = f"{current_year}-unknown"
            day_name = day_label
            m = re.search(r"([A-Za-z]+)\s+(\d{1,2})/(\d{1,2})", day_label)
            if m:
                day_name = m.group(1)
                day_num = int(m.group(2))
                month_num = int(m.group(3))
                date_str = f"{current_year:04d}-{month_num:02d}-{day_num:02d}"

            lessons: List[Lesson] = []
            brik_gruppe = dag.find("g", class_="skemaBrikGruppe")
            if brik_gruppe:
                for b in brik_gruppe.find_all(recursive=False):
                    lesson = self.parse_tile(b, day_date=date_str, day_name=day_name)
                    lessons.append(lesson)

            week_days.append(DaySchedule(
                date=date_str,
                day_name=day_name,
                lessons=lessons
            ))

        week_info_match = re.search(r"(Week\s+\d+\s*-\s*\d{4})", header_text, re.IGNORECASE)
        week_info = week_info_match.group(1) if week_info_match else None

        return WeekSchedule(week_info=week_info, days=week_days)

    def apply_assignment_filters(
        self,
        show_open: bool = True,
        show_handed_in: bool = False,
        show_graded: bool = False,
        show_lackingupload: bool = False,
    ) -> None:
        """Configures the checkbox filters on the assignment overview."""
        self.check_auth()
        WebDriverWait(self.driver, 15).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, "input[type=checkbox]")) >= 4
        )

        desired_states = {
            "show open": show_open,
            "show handed in": show_handed_in,
            "show graded": show_graded,
            "show lackingupload": show_lackingupload,
        }

        checkboxes = self.driver.find_elements(By.CSS_SELECTOR, "input[type=checkbox]")
        changed = False
        for cb in checkboxes:
            try:
                parent_text = cb.find_element(By.XPATH, "..").text.strip().lower()
                for key, want_checked in desired_states.items():
                    if key in parent_text:
                        is_checked = cb.is_selected()
                        if is_checked != want_checked:
                            self.driver.execute_script("arguments[0].click();", cb)
                            changed = True
            except Exception:
                pass

        if changed:
            time.sleep(2.5)

    def parse_assignments_overview(self) -> List[Tuple[Assignment, Any]]:
        """
        Parses the assignments table rows with dynamic column detection.
        Returns a list of tuples: (Assignment, selenium_details_button_or_None).
        """
        self.check_auth()
        WebDriverWait(self.driver, 15).until(
            lambda d: len(d.find_elements(By.TAG_NAME, "table")) > 0
        )
        time.sleep(1)

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        table = soup.find("table")
        if not table:
            return []

        rows = table.find_all("tr")
        detail_buttons = [
            b for b in self.driver.find_elements(By.TAG_NAME, "button")
            if b.text.strip() == "Details"
        ]

        header_row = None
        for r in rows:
            cell_texts = [c.get_text(strip=True).lower() for c in r.find_all(["th", "td"])]
            if "subject" in cell_texts and ("assignment title" in cell_texts or "title" in cell_texts):
                header_row = cell_texts
                break

        col_map = {}
        if header_row:
            for idx, text in enumerate(header_row):
                if "subject" in text:
                    col_map["subject"] = idx
                elif "title" in text:
                    col_map["title"] = idx
                elif "pulje" in text:
                    col_map["pulje"] = idx
                elif "brugt" in text:
                    col_map["brugt"] = idx
                elif "class" in text:
                    col_map["class"] = idx
                elif "week" in text:
                    col_map["week"] = idx
                elif "handed in" in text:
                    col_map["due_date"] = idx
                elif "submitted" in text:
                    col_map["submitted"] = idx
                elif "grade" in text:
                    col_map["grade"] = idx

        assignments_with_buttons: List[Tuple[Assignment, Any]] = []
        detail_btn_idx = 0

        for r in rows:
            cells = [td.get_text(strip=True) for td in r.find_all(["td", "th"])]
            if len(cells) < 6:
                continue

            if "Subject" in cells or "You have no assignments" in cells[0]:
                continue

            def get_val(k):
                i = col_map.get(k)
                if i is not None and i < len(cells):
                    v = cells[i].strip()
                    if v and v.lower() != "details":
                        return v
                return None

            subject = get_val("subject") or cells[0]
            title = get_val("title") or cells[1]

            pulje_str = get_val("pulje")
            pulje = float(pulje_str) if pulje_str and pulje_str.replace(".", "", 1).isdigit() else None

            brugt_str = get_val("brugt")
            brugt = float(brugt_str) if brugt_str and brugt_str.replace(".", "", 1).isdigit() else None

            class_group = get_val("class")
            week_str = get_val("week")
            week = int(week_str) if week_str and week_str.isdigit() else None
            due_date = get_val("due_date")
            submitted_date = get_val("submitted")
            grade = get_val("grade")

            status = "open"
            if grade and grade.lower() not in ("ingen karakter", ""):
                status = "graded"
            elif submitted_date:
                status = "submitted"
            elif grade and grade.lower() == "ingen karakter":
                status = "submitted"

            due_dt = parse_danish_datetime(due_date)
            due_date_iso = due_dt.isoformat() if due_dt else None

            assignment = Assignment(
                subject=subject,
                title=title,
                student_time_allocated=pulje,
                student_time_used=brugt,
                class_group=class_group,
                week=week,
                due_date=due_date,
                due_date_iso=due_date_iso,
                submitted_date=submitted_date,
                grade=grade,
                status=status,
            )

            btn = detail_buttons[detail_btn_idx] if detail_btn_idx < len(detail_buttons) else None
            detail_btn_idx += 1

            assignments_with_buttons.append((assignment, btn))

        return assignments_with_buttons

    def populate_details(self, assignment: Assignment, button, download_files: bool = False) -> None:
        """Clicks details on an assignment, extracts description and files, and returns to overview."""
        if not button:
            return

        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            self.driver.execute_script("arguments[0].click();", button)

            WebDriverWait(self.driver, 10).until(
                lambda d: len(d.find_elements(By.XPATH, "//button[contains(text(), 'To assignment overview')]")) > 0
            )
            time.sleep(1)

            rt_elements = self.driver.find_elements(By.CSS_SELECTOR, ".gwt-RichTextArea")
            if rt_elements:
                desc = self.driver.execute_script("""
                    const el = arguments[0];
                    try {
                        if (el.contentDocument && el.contentDocument.body) {
                            return el.contentDocument.body.innerText;
                        }
                    } catch(e) {}
                    return el.innerText;
                """, rt_elements[0])
                if desc and desc.strip() != "No description":
                    assignment.description = desc.strip()

            file_anchors = self.driver.find_elements(By.CSS_SELECTOR, "a.gwt-Anchor[title]")
            for fa in file_anchors:
                fname = fa.get_attribute("title")
                if fname and fname not in assignment.files:
                    assignment.files.append(fname)
                    if download_files:
                        fa.click()
                        time.sleep(1)

            back_btn = self.driver.find_element(By.XPATH, "//button[contains(text(), 'To assignment overview')]")
            self.driver.execute_script("arguments[0].click();", back_btn)
            WebDriverWait(self.driver, 10).until(
                lambda d: len(d.find_elements(By.TAG_NAME, "table")) > 0
            )
            time.sleep(0.5)

        except Exception:
            pass

    def wait_for_conversations_render(self, timeout: int = 15) -> None:
        """Waits until the conversation list container is rendered in the DOM."""
        self.check_auth()
        WebDriverWait(self.driver, timeout).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, ".ps-container .BP00PUB-b-d")) > 0
        )
        time.sleep(1)

    def parse_conversations(
        self,
        limit: int = 15,
        with_content: bool = True,
        view_all: bool = False
    ) -> List[Conversation]:
        """
        Parses conversations and announcements from Studie+.
        If view_all is True, switches from 'Applicable conversations (last 14 days)' to 'All conversations'.
        If with_content is True, clicks each item to extract full body, thread comments, and attachments.
        """
        self.wait_for_conversations_render()

        if view_all:
            try:
                view_btns = self.driver.find_elements(By.XPATH, "//button[contains(text(), 'View')]")
                if view_btns:
                    self.driver.execute_script("arguments[0].click();", view_btns[0])
                    time.sleep(1)
                    all_conv_links = self.driver.find_elements(By.XPATH, "//a[contains(text(), 'All conversations')]")
                    if all_conv_links:
                        self.driver.execute_script("arguments[0].click();", all_conv_links[0])
                        time.sleep(2)
            except Exception:
                pass

        items = self.driver.find_elements(By.CSS_SELECTOR, ".ps-container .BP00PUB-b-d")
        if not items:
            return []

        limit_to_process = min(limit, len(items))
        conversations: List[Conversation] = []

        for idx in range(limit_to_process):
            current_items = self.driver.find_elements(By.CSS_SELECTOR, ".ps-container .BP00PUB-b-d")
            if idx >= len(current_items):
                break
            item = current_items[idx]

            sender = ""
            date_str = ""
            subject = ""
            preview = ""
            conv_id = None

            try:
                sender_el = item.find_element(By.CSS_SELECTOR, ".BP00PUB-b-c")
                sender = sender_el.text.strip()
            except Exception:
                pass

            try:
                date_el = item.find_element(By.CSS_SELECTOR, ".BP00PUB-b-i")
                date_str = date_el.text.strip()
            except Exception:
                pass

            try:
                q_spans = item.find_elements(By.CSS_SELECTOR, ".BP00PUB-b-q")
                if len(q_spans) > 0:
                    subject = html.unescape(q_spans[0].text.strip())
                if len(q_spans) > 1:
                    preview = html.unescape(q_spans[1].text.strip())
            except Exception:
                pass

            try:
                imgs = item.find_elements(By.CSS_SELECTOR, "img.gwt-Image")
                for img in imgs:
                    src = img.get_attribute("src") or ""
                    m = re.search(r"samt_id=(\d+)", src)
                    if m:
                        conv_id = m.group(1)
                        break
            except Exception:
                pass

            sender_initials = get_initials_for_teacher(sender)

            conv = Conversation(
                id=conv_id,
                sender=sender,
                sender_name=sender,
                date=date_str,
                subject=subject,
                preview=preview,
            )

            if with_content:
                try:
                    self.driver.execute_script("arguments[0].click();", item)
                    time.sleep(1.5)

                    soup = BeautifulSoup(self.driver.page_source, "html.parser")
                    containers = soup.find_all(class_=lambda x: x and "ps-container" in x)

                    body_el = soup.find(class_=lambda x: x and "BP00PUB-y-a" in x)
                    if body_el:
                        raw_body = body_el.get_text("\n", strip=True)
                        cleaned_body = re.sub(r"[ \t]+", " ", raw_body)
                        conv.content = html.unescape(cleaned_body)

                    files_found = []
                    for c_idx in [1, 2]:
                        if c_idx < len(containers):
                            fc = containers[c_idx]
                            for fa in fc.find_all("a"):
                                ftitle = fa.get("title") or fa.get_text(strip=True)
                                if ftitle and ftitle not in ["Filter by type", "javascript:;"] and not ftitle.startswith("javascript:"):
                                    if ftitle not in files_found:
                                        files_found.append(ftitle)
                    conv.files = files_found

                    if len(containers) > 3:
                        c3 = containers[3]
                        c3_text = c3.get_text("\n", strip=True)
                        if "Nobody can comment" in c3_text:
                            conv.is_announcement = True

                        comment_spans = c3.find_all("span", class_=lambda x: x and "BP00PUB-b-c" in x and "BP00PUB-b-s" in x)
                        for cspan in comment_spans:
                            c_author = cspan.get_text(strip=True)
                            c_parent = cspan.find_parent("div")
                            c_content = ""
                            if c_parent:
                                c_full = c_parent.get_text(" ", strip=True)
                                c_content = c_full.replace(c_author, "", 1).strip()
                            if c_author and c_content:
                                cleaned_c_content = html.unescape(re.sub(r"[ \t]+", " ", c_content))
                                conv.comments.append(ConversationComment(
                                    author=c_author,
                                    content=cleaned_c_content
                                ))
                except Exception:
                    pass

            conversations.append(conv)

        return conversations
