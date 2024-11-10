import flet as ft

from data.constants import PROJECT_FOLDER
from .colors import PURPLE


# <! ---------------------- Classes ---------------------- !>
class ViewS(ft.View):
    def __init__(self, controls):
        super().__init__(controls=controls)
        self.appbar = navigation


class PersonRow(ft.Row):
    def __init__(self, text):
        super().__init__(
            controls=[
                ft.ListTile(
                    trailing=ft.Icon(
                        ft.icons.PERSON,
                        size=32
                    ),
                    title=ft.Text(
                        text,
                        text_align=ft.TextAlign.RIGHT
                    ),
                    width=335
                )
            ],
            alignment=ft.MainAxisAlignment.END
        )


class AnswerRow(ft.Row):
    def __init__(self):
        super().__init__(
            controls=[
                ft.ListTile(
                    leading=ft.Icon(
                        ft.icons.COMPUTER,
                        size=32
                    ),
                    title=ft.Markdown("##### Processing 🌍 "),
                    width=335
                )
            ],
            alignment=ft.MainAxisAlignment.START
        )


# <! ---------------------- Images ---------------------- !>

assistant_gif = ft.Card(ft.Image(
    src=f"{PROJECT_FOLDER}/gui/assets/animations/assistant.gif",
    width=150,
    height=120,
    fit=ft.ImageFit.CONTAIN,
), elevation=3, shadow_color=PURPLE)

loading_gif = ft.Image(
    src=f"{PROJECT_FOLDER}/gui/assets/animations/loading.gif",
    fit=ft.ImageFit.CONTAIN,
)

# <! ---------------------- Navigation bar ---------------------- !>

navigation = ft.AppBar(
    leading=ft.Image(f"{PROJECT_FOLDER}/data/images/stewart_logo.png", height=75),
    leading_width=240,
    actions=[
        ft.IconButton(ft.icons.HOME, tooltip="Home page", data="home", icon_size=29),
        ft.IconButton(ft.icons.CREATE, tooltip="Create new commands", data="create",
                      icon_size=29),
        ft.IconButton(ft.icons.ACCOUNT_TREE, tooltip="Command tree", icon_size=29),
        ft.PopupMenuButton(
            icon=ft.icons.SETTINGS,
            padding=10,
            items=[
                ft.PopupMenuItem(icon=ft.icons.APPS, text="Configuration"),
                ft.PopupMenuItem(icon=ft.icons.MIC, text="Audio"),
                ft.PopupMenuItem(icon=ft.icons.COMPUTER, text="App"),
                ft.PopupMenuItem(icon=ft.icons.ADD_BOX, text="Plugins"),
                ft.PopupMenuItem(),
                ft.PopupMenuItem(icon=ft.icons.CODE, text="For developers"),
                ft.PopupMenuItem(),
                ft.PopupMenuItem(icon=ft.icons.INFO, text="About")
            ],
            icon_size=29
        )
    ],
    toolbar_height=75,
)

# <! ---------------------- Home chat window ---------------------- !>

chat_messages = ft.Column(
    scroll=ft.ScrollMode.HIDDEN,
    auto_scroll=True,
)

input_field = ft.TextField(
    width=250,
    border_radius=10,
    border_color=PURPLE,
    border_width=1.5,
    label_style=ft.TextStyle(size=15)
)

send_button = ft.IconButton(
    ft.icons.SEND,
    icon_size=28,
    padding=8,
    icon_color=PURPLE
)

mic_button = ft.IconButton(
    ft.icons.MIC,
    icon_size=28,
    padding=8,
    icon_color=PURPLE
)

# <! ---------------------- Widgets ---------------------- !>

output_widget = ft.Card(
    ft.Container(
        ft.Column(
            [
            ],
            auto_scroll=True
        )
    ),
    width=1024,
    height=90
)

# <! ---------------------- Views ---------------------- !>


home_view = ViewS(
    controls=[
        ft.Column([
            ft.Row([  # Main row
                ft.Card(
                    content=ft.Container(
                        ft.Column(
                            [
                                ft.Container(
                                    content=chat_messages,
                                    width=350,
                                    height=440,
                                ),

                                ft.Row(
                                    [
                                        input_field,
                                        mic_button,
                                        send_button
                                    ],
                                    alignment=ft.MainAxisAlignment.START,
                                    spacing=4
                                )
                            ]
                        ),
                        padding=10
                    ),
                    shadow_color=PURPLE,
                    elevation=3
                ),
                ft.Column(
                    [
                        assistant_gif
                    ],
                    alignment=ft.MainAxisAlignment.END,
                    height=527
                )
            ]),
            ft.Row([
                output_widget
            ])
        ])
    ]
)

loading_view = ft.View(
    controls=[
        ft.Row([
            loading_gif
        ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
    ]
)


