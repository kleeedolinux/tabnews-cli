import requests
import json
import os
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.table import Table
from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, HSplit, VSplit
from prompt_toolkit.widgets import TextArea, Frame, Button
from prompt_toolkit.styles import Style
from prompt_toolkit.layout.containers import Window, WindowAlign, ConditionalContainer
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.filters import Condition
import asyncio
from typing import List, Dict, Any
import markdown2
import re
import textwrap
import math

console = Console()
BASE_URL = "https://www.tabnews.com.br/api/v1"

class TabNewsAPI:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        load_dotenv()
        self.token = os.getenv("TABNEWS_TOKEN")

    def get_contents(self, page: int = 1, per_page: int = 10, strategy: str = "relevant"):
        url = f"{BASE_URL}/contents"
        params = {
            "page": page,
            "per_page": per_page,
            "strategy": strategy
        }
        response = self.session.get(url, params=params)
        if response.status_code != 200:
            error_data = response.json()
            error_message = error_data.get("message", "Unknown error")
            raise Exception(f"API Error ({response.status_code}): {error_message}")
        return response.json()

    def get_user_contents(self, username: str, page: int = 1, per_page: int = 10, strategy: str = "relevant"):
        url = f"{BASE_URL}/contents/{username}"
        params = {
            "page": page,
            "per_page": per_page,
            "strategy": strategy
        }
        response = self.session.get(url, params=params)
        if response.status_code != 200:
            error_data = response.json()
            error_message = error_data.get("message", "Unknown error")
            raise Exception(f"API Error ({response.status_code}): {error_message}")
        return response.json()

    def get_content(self, username: str, slug: str):
        url = f"{BASE_URL}/contents/{username}/{slug}"
        response = self.session.get(url)
        if response.status_code != 200:
            error_data = response.json()
            error_message = error_data.get("message", "Unknown error")
            raise Exception(f"API Error ({response.status_code}): {error_message}")
        return response.json()

    def get_comments(self, username: str, slug: str):
        url = f"{BASE_URL}/contents/{username}/{slug}/children"
        response = self.session.get(url)
        if response.status_code != 200:
            error_data = response.json()
            error_message = error_data.get("message", "Unknown error")
            raise Exception(f"API Error ({response.status_code}): {error_message}")
        return response.json()

    def login(self, email: str, password: str):
        url = f"{BASE_URL}/sessions"
        data = {
            "email": email,
            "password": password
        }
        response = self.session.post(url, json=data)
        if response.status_code == 200:
            self.token = response.json().get("token")
            return True
        return False

class TabNewsUI:
    def __init__(self):
        self.api = TabNewsAPI()
        self.current_page = 1
        self.current_strategy = "relevant"
        self.selected_index = 0
        self.contents = []
        self.current_content = None
        self.view_mode = "feed"  
        self.content_scroll_position = 0
        self.comments = []
        self.terminal_width = 80
        self.terminal_height = 24
        self.content_pages = []
        self.current_content_page = 0
        self.setup_ui()

    def setup_ui(self):
        self.kb = KeyBindings()
        
        @self.kb.add('up')
        def _(event):
            if self.view_mode == "feed":
                self.selected_index = max(0, self.selected_index - 1)
                self.update_feed()
            elif self.view_mode == "content":
                self.current_content_page = max(0, self.current_content_page - 1)
                self.update_content_view()
            event.app.invalidate()

        @self.kb.add('down')
        def _(event):
            if self.view_mode == "feed":
                self.selected_index = min(len(self.contents) - 1, self.selected_index + 1)
                self.update_feed()
            elif self.view_mode == "content":
                self.current_content_page = min(len(self.content_pages) - 1, self.current_content_page + 1)
                self.update_content_view()
            event.app.invalidate()

        @self.kb.add('left')
        def _(event):
            if self.view_mode == "feed":
                if self.current_page > 1:
                    self.current_page -= 1
                    self.selected_index = 0
                    self.update_feed()
            event.app.invalidate()

        @self.kb.add('right')
        def _(event):
            if self.view_mode == "feed":
                self.current_page += 1
                self.selected_index = 0
                self.update_feed()
            event.app.invalidate()

        @self.kb.add('enter')
        def _(event):
            if self.view_mode == "feed" and self.contents:
                content = self.contents[self.selected_index]
                self.show_content(content)
            elif self.view_mode == "content":
                self.show_comments()
            event.app.invalidate()

        @self.kb.add('escape')
        def _(event):
            if self.view_mode == "content":
                self.view_mode = "feed"
                self.update_feed()
            elif self.view_mode == "comments":
                self.view_mode = "content"
                self.update_content_view()
            event.app.invalidate()

        @self.kb.add('q')
        def _(event):
            event.app.exit()

        @self.kb.add('c')
        def _(event):
            if self.view_mode == "content":
                self.show_comments()
            event.app.invalidate()

        self.feed_control = FormattedTextControl("")
        self.content_control = FormattedTextControl("")
        self.comments_control = FormattedTextControl("")
        
        
        self.header_window = Window(
            height=1,
            content=FormattedTextControl("TabNews CLI - ↑↓: Navigate | ←→: Pages | Enter: Select | Esc: Back | C: Comments | Q: Quit"),
            style="class:header"
        )
        
        self.feed_window = Window(
            content=self.feed_control,
            style="class:feed"
        )
        
        self.content_window = Window(
            content=self.content_control,
            style="class:content"
        )
        
        self.comments_window = Window(
            content=self.comments_control,
            style="class:comments"
        )

        
        self.is_feed = Condition(lambda: self.view_mode == "feed")
        self.is_content = Condition(lambda: self.view_mode == "content")
        self.is_comments = Condition(lambda: self.view_mode == "comments")

        
        self.feed_container = ConditionalContainer(
            self.feed_window,
            filter=self.is_feed
        )
        
        self.content_container = ConditionalContainer(
            self.content_window,
            filter=self.is_content
        )
        
        self.comments_container = ConditionalContainer(
            self.comments_window,
            filter=self.is_comments
        )
        
        self.layout = Layout(
            HSplit([
                self.header_window,
                self.feed_container,
                self.content_container,
                self.comments_container
            ])
        )

        self.style = Style.from_dict({
            'header': 'bg:ansiblue fg:white',
            'feed': 'bg:ansiblack fg:white',
            'content': 'bg:ansiblack fg:white',
            'comments': 'bg:ansiblack fg:white',
            'title': 'bold fg:ansiyellow',
            'author': 'italic fg:ansigreen',
            'date': 'fg:ansicyan',
            'comment': 'fg:ansiyellow',
            'page': 'bold fg:ansiyellow',
            'separator': 'fg:ansiblue',
            'page_number': 'fg:ansicyan'
        })

        self.app = Application(
            layout=self.layout,
            key_bindings=self.kb,
            style=self.style,
            full_screen=True
        )

    def wrap_text(self, text, width=80):
        return textwrap.fill(text, width=width)

    def format_markdown(self, text):
        html = markdown2.markdown(text)
        return HTML(html)

    def split_into_pages(self, text, width=80, height=20):
        wrapped_text = self.wrap_text(text, width=width)
        lines = wrapped_text.split('\n')
        pages = []
        current_page = []
        current_height = 0

        for line in lines:
            if current_height >= height:
                pages.append('\n'.join(current_page))
                current_page = []
                current_height = 0
            current_page.append(line)
            current_height += 1

        if current_page:
            pages.append('\n'.join(current_page))

        return pages

    def update_feed(self):
        feed_text = []
        
        feed_text.append(f"[page]Page {self.current_page}[/page]")
        feed_text.append("")
        
        try:
            self.contents = self.api.get_contents(self.current_page, 10, self.current_strategy)
            
            for i, content in enumerate(self.contents):
                prefix = "→ " if i == self.selected_index else "  "
                title = self.wrap_text(content['title'], width=self.terminal_width - 4)
                author = content['owner_username']
                feed_text.append(f"{prefix}{title}")
                feed_text.append(f"    by {author}")
                feed_text.append("")
        except Exception as e:
            # Handle API errors and display them nicely in the feed view
            error_message = str(e)
            wrapped_error = self.wrap_text(error_message, width=self.terminal_width - 4)
            feed_text.append("[title]Error fetching content[/title]")
            feed_text.append("")
            feed_text.append(wrapped_error)
            feed_text.append("")
            feed_text.append("Try again later or change page.")
            self.contents = []  # Reset contents to empty list
        
        self.feed_control.text = "\n".join(feed_text)
        self.content_control.text = ""
        self.comments_control.text = ""

    def show_content(self, content):
        self.view_mode = "content"
        self.current_content_page = 0
        try:
            full_content = self.api.get_content(content["owner_username"], content["slug"])
            self.current_content = full_content
            self.prepare_content_pages()
            self.update_content_view()
        except Exception as e:
            error_message = str(e)
            self.content_pages = []
            error_content = [
                f"[title]Error loading content[/title]",
                "",
                self.wrap_text(error_message, width=self.terminal_width - 4),
                "",
                "Press Esc to go back to the feed."
            ]
            self.content_pages.append("\n".join(error_content))
            self.update_content_view()

    def prepare_content_pages(self):
        if not self.current_content:
            return

        content = self.current_content
        title = self.wrap_text(content['title'], width=self.terminal_width - 4)
        author = content['owner_username']
        date = content['created_at']
        
        
        body_pages = self.split_into_pages(
            content['body'],
            width=self.terminal_width - 4,
            height=self.terminal_height - 6  
        )
        
        self.content_pages = []
        for i, page in enumerate(body_pages):
            page_content = [
                f"[title]{title}[/title]",
                f"[author]by {author}[/author] | [date]{date}[/date]",
                "",
                "[separator]" + "─" * (self.terminal_width - 4) + "[/separator]",
                "",
                page,
                "",
                f"[page_number]Page {i + 1} of {len(body_pages)}[/page_number]"
            ]
            self.content_pages.append("\n".join(page_content))

    def update_content_view(self):
        if not self.content_pages:
            return

        self.content_control.text = self.content_pages[self.current_content_page]
        self.comments_control.text = ""

    def show_comments(self):
        if not self.current_content:
            return

        self.view_mode = "comments"
        comments_text = []
        
        try:
            comments = self.api.get_comments(
                self.current_content["owner_username"],
                self.current_content["slug"]
            )
            
            for comment in comments:
                author = comment['owner_username']
                date = comment['created_at']
                body = self.wrap_text(comment['body'], width=self.terminal_width - 4)
                
                comments_text.extend([
                    f"[author]{author}[/author] | [date]{date}[/date]",
                    "",
                    body,
                    "",
                    "[separator]" + "─" * (self.terminal_width - 4) + "[/separator]",
                    ""
                ])
        except Exception as e:
            error_message = str(e)
            comments_text = [
                "[title]Error loading comments[/title]",
                "",
                self.wrap_text(error_message, width=self.terminal_width - 4),
                "",
                "Press Esc to go back to the content."
            ]
            
        self.comments_control.text = "\n".join(comments_text)
        self.content_control.text = ""

    def run(self):
        self.update_feed()
        self.app.run()

if __name__ == "__main__":
    ui = TabNewsUI()
    ui.run() 