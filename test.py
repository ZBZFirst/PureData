import pygame
import os
import sys

# Initialize Pygame and mixer
pygame.init()
pygame.mixer.init()

# Constants
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
SIDEBAR_WIDTH = 300
FILE_LIST_HEIGHT = 600
FONT_SIZE = 16
TITLE_FONT_SIZE = 24
ITEM_HEIGHT = 30
INDENT_SIZE = 20

# Colors
DARK_BG = (30, 30, 40)
LIGHT_BG = (45, 45, 55)
ACCENT = (86, 98, 246)
ACCENT_HOVER = (106, 118, 266)
SUCCESS = (76, 175, 80)
WARNING = (255, 152, 0)
TEXT_WHITE = (240, 240, 240)
TEXT_GRAY = (180, 180, 190)
TEXT_LIGHT = (200, 200, 210)
SCROLLBAR_BG = (60, 60, 70)
SCROLLBAR_THUMB = (100, 100, 120)

class FileItem:
    def __init__(self, name, path, is_dir, depth=0, parent=None):
        self.name = name
        self.path = path
        self.is_dir = is_dir
        self.depth = depth
        self.parent = parent
        self.children = []
        self.expanded = False
        self.loaded = False

class AudioBrowser:
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.current_dir = root_dir
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Sample Browser • SuperCollider Samples")
        self.font = pygame.font.SysFont('Segoe UI', FONT_SIZE)
        self.title_font = pygame.font.SysFont('Segoe UI', TITLE_FONT_SIZE, bold=True)
        self.small_font = pygame.font.SysFont('Segoe UI', FONT_SIZE - 2)

        # File browser state
        self.root_item = FileItem("Dirt-Samples", root_dir, True, 0)
        self.flat_items = []
        self.selected_item = None
        self.currently_playing = None
        self.scroll_offset = 0
        self.max_visible_items = (SCREEN_HEIGHT - 50) // ITEM_HEIGHT

        # Load initial directory
        self.load_directory(self.root_item)

    def load_directory(self, parent_item):
        """Load directory contents into a FileItem"""
        try:
            items = []
            # Get all items in directory
            for item_name in os.listdir(parent_item.path):
                item_path = os.path.join(parent_item.path, item_name)
                if os.path.isdir(item_path) or (os.path.isfile(item_path) and item_name.lower().endswith('.wav')):
                    items.append((item_name, item_path, os.path.isdir(item_path)))

            # Sort: directories first, then files
            items.sort(key=lambda x: (not x[2], x[0].lower()))  # dirs first, then alphabetical

            parent_item.children = []
            for name, path, is_dir in items:
                child_item = FileItem(name, path, is_dir, parent_item.depth + 1, parent_item)
                parent_item.children.append(child_item)

            parent_item.loaded = True
        except PermissionError:
            pass

    def get_flat_items(self, item=None, visible=True):
        """Get flattened list of visible items for display"""
        if item is None:
            item = self.root_item
            self.flat_items = []

        if visible:
            self.flat_items.append(item)

        if item.is_dir and item.expanded:
            for child in item.children:
                self.get_flat_items(child, True)

        return self.flat_items

    def find_item_by_path(self, path, items=None):
        """Find a FileItem by its path"""
        if items is None:
            items = [self.root_item]

        for item in items:
            if item.path == path:
                return item
            if item.is_dir and item.children:
                found = self.find_item_by_path(path, item.children)
                if found:
                    return found
        return None

    def play_audio(self, filename, path):
        """Play the selected audio file"""
        try:
            # Stop currently playing sound
            if self.currently_playing:
                pygame.mixer.music.stop()

            # Load and play new sound
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            self.currently_playing = filename
            return True
        except pygame.error as e:
            print(f"Error playing {filename}: {e}")
            return False

    def draw_sidebar(self):
        """Draw the sidebar with navigation and info"""
        # Sidebar background
        pygame.draw.rect(self.screen, LIGHT_BG, (0, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT))

        # Title
        title = self.title_font.render("Sample Browser", True, TEXT_WHITE)
        self.screen.blit(title, (20, 20))

        # Subtitle
        subtitle = self.small_font.render("SuperCollider Samples", True, TEXT_GRAY)
        self.screen.blit(subtitle, (20, 55))

        # Stats
        flat_items = self.get_flat_items()
        dirs = [f for f in flat_items if f.is_dir]
        wavs = [f for f in flat_items if not f.is_dir]

        stats_text = [
            f"Folders: {len(dirs)}",
            f"Samples: {len(wavs)}",
            f"Visible: {len(flat_items)} items"
        ]

        for i, stat in enumerate(stats_text):
            stat_surf = self.small_font.render(stat, True, TEXT_LIGHT)
            self.screen.blit(stat_surf, (20, 100 + i * 25))

        # Currently playing
        if self.currently_playing:
            playing_label = self.small_font.render("Now Playing:", True, TEXT_GRAY)
            self.screen.blit(playing_label, (20, 180))

            playing_text = self.font.render(self.currently_playing, True, SUCCESS)
            self.screen.blit(playing_text, (20, 200))

        # Controls section
        controls_title = self.small_font.render("Controls:", True, TEXT_GRAY)
        self.screen.blit(controls_title, (20, 250))

        controls = [
            "Click file - Play sample",
            "Click folder - Expand/collapse",
            "↑↓ - Navigate list",
            "Enter - Expand/collapse folder",
            "Space - Play selected",
            "P - Stop playback",
            "Mouse wheel - Scroll",
            "Esc - Collapse all"
        ]

        for i, control in enumerate(controls):
            control_surf = self.small_font.render(control, True, TEXT_LIGHT)
            self.screen.blit(control_surf, (20, 275 + i * 20))

    def draw_scrollbar(self, total_items):
        """Draw the scrollbar"""
        scrollbar_width = 12
        scrollbar_x = SCREEN_WIDTH - scrollbar_width - 5

        # Calculate scrollbar proportions
        visible_ratio = min(1.0, self.max_visible_items / total_items)
        thumb_height = max(30, FILE_LIST_HEIGHT * visible_ratio)

        # Calculate thumb position
        max_scroll = max(0, total_items - self.max_visible_items)
        if max_scroll > 0:
            thumb_position = (self.scroll_offset / max_scroll) * (FILE_LIST_HEIGHT - thumb_height)
        else:
            thumb_position = 0

        # Draw scrollbar background
        pygame.draw.rect(self.screen, SCROLLBAR_BG,
                        (scrollbar_x, 50, scrollbar_width, FILE_LIST_HEIGHT))

        # Draw scrollbar thumb
        pygame.draw.rect(self.screen, SCROLLBAR_THUMB,
                        (scrollbar_x, 50 + thumb_position, scrollbar_width, thumb_height),
                        border_radius=6)

    def draw_file_list(self):
        """Draw the main file list"""
        # Main content area background
        pygame.draw.rect(self.screen, DARK_BG, (SIDEBAR_WIDTH, 0, SCREEN_WIDTH - SIDEBAR_WIDTH, SCREEN_HEIGHT))

        # Header
        header_bg = pygame.Rect(SIDEBAR_WIDTH, 0, SCREEN_WIDTH - SIDEBAR_WIDTH, 40)
        pygame.draw.rect(self.screen, LIGHT_BG, header_bg)

        header_text = self.font.render("Samples & Folders", True, TEXT_WHITE)
        self.screen.blit(header_text, (SIDEBAR_WIDTH + 20, 10))

        # Get visible items
        flat_items = self.get_flat_items()
        total_items = len(flat_items)

        # Draw scrollbar
        self.draw_scrollbar(total_items)

        # Calculate visible range
        start_idx = self.scroll_offset
        end_idx = min(start_idx + self.max_visible_items, total_items)

        # Draw visible items
        y_pos = 50
        for i in range(start_idx, end_idx):
            if i >= len(flat_items):
                break

            item = flat_items[i]
            item_rect = pygame.Rect(SIDEBAR_WIDTH + 10 + (item.depth * INDENT_SIZE),
                                  y_pos,
                                  SCREEN_WIDTH - SIDEBAR_WIDTH - 30 - (item.depth * INDENT_SIZE),
                                  ITEM_HEIGHT)

            # Background
            if item == self.selected_item:
                pygame.draw.rect(self.screen, ACCENT, item_rect, border_radius=4)
                color = TEXT_WHITE
            elif item.name == self.currently_playing:
                pygame.draw.rect(self.screen, (76, 175, 80, 50), item_rect, border_radius=4)
                color = SUCCESS
            else:
                color = TEXT_LIGHT

            # Icon and text
            if item.is_dir:
                icon = "▶" if not item.expanded else "▼"
            else:
                icon = "●"

            display_text = f"{icon} {item.name}"

            file_text = self.font.render(display_text, True, color)
            self.screen.blit(file_text, (SIDEBAR_WIDTH + 25 + (item.depth * INDENT_SIZE), y_pos + 7))

            y_pos += ITEM_HEIGHT

    def draw(self):
        """Draw the entire interface"""
        self.screen.fill(DARK_BG)
        self.draw_sidebar()
        self.draw_file_list()
        pygame.display.flip()

    def handle_mouse_scroll(self, event):
        """Handle mouse wheel scrolling"""
        flat_items = self.get_flat_items()
        total_items = len(flat_items)
        max_scroll = max(0, total_items - self.max_visible_items)

        if event.y > 0:  # Scroll up
            self.scroll_offset = max(0, self.scroll_offset - 3)
        elif event.y < 0:  # Scroll down
            self.scroll_offset = min(max_scroll, self.scroll_offset + 3)

    def ensure_visible(self, item_index):
        """Ensure the item at given index is visible in viewport"""
        flat_items = self.get_flat_items()
        if item_index < self.scroll_offset:
            self.scroll_offset = max(0, item_index)
        elif item_index >= self.scroll_offset + self.max_visible_items:
            self.scroll_offset = min(len(flat_items) - self.max_visible_items,
                                   item_index - self.max_visible_items + 1)

    def run(self):
        """Main game loop"""
        running = True
        clock = pygame.time.Clock()

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.MOUSEWHEEL:
                    self.handle_mouse_scroll(event)

                elif event.type == pygame.KEYDOWN:
                    flat_items = self.get_flat_items()

                    if event.key == pygame.K_ESCAPE:
                        # Collapse all folders
                        def collapse_all(item):
                            item.expanded = False
                            for child in item.children:
                                if child.is_dir:
                                    collapse_all(child)
                        collapse_all(self.root_item)
                        self.scroll_offset = 0

                    elif event.key == pygame.K_UP and flat_items:
                        # Navigate up
                        if self.selected_item:
                            current_idx = flat_items.index(self.selected_item)
                            new_idx = max(0, current_idx - 1)
                            self.selected_item = flat_items[new_idx]
                            self.ensure_visible(new_idx)
                        else:
                            self.selected_item = flat_items[0]

                    elif event.key == pygame.K_DOWN and flat_items:
                        # Navigate down
                        if self.selected_item:
                            current_idx = flat_items.index(self.selected_item)
                            new_idx = min(len(flat_items) - 1, current_idx + 1)
                            self.selected_item = flat_items[new_idx]
                            self.ensure_visible(new_idx)
                        else:
                            self.selected_item = flat_items[0]

                    elif event.key == pygame.K_RETURN and self.selected_item:
                        # Expand/collapse selected folder
                        if self.selected_item.is_dir:
                            if not self.selected_item.loaded:
                                self.load_directory(self.selected_item)
                            self.selected_item.expanded = not self.selected_item.expanded
                            # Reset flat items
                            self.get_flat_items()

                    elif event.key == pygame.K_SPACE and self.selected_item:
                        # Play selected file
                        if not self.selected_item.is_dir:
                            self.play_audio(self.selected_item.name, self.selected_item.path)

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        mouse_x, mouse_y = pygame.mouse.get_pos()

                        # Check if click is in file list area
                        if (mouse_x > SIDEBAR_WIDTH and mouse_x < SCREEN_WIDTH - 20 and
                            mouse_y > 50 and mouse_y < SCREEN_HEIGHT):

                            flat_items = self.get_flat_items()
                            item_index = self.scroll_offset + (mouse_y - 50) // ITEM_HEIGHT

                            if item_index < len(flat_items):
                                clicked_item = flat_items[item_index]
                                self.selected_item = clicked_item

                                if clicked_item.is_dir:
                                    # Expand/collapse folder
                                    if not clicked_item.loaded:
                                        self.load_directory(clicked_item)
                                    clicked_item.expanded = not clicked_item.expanded
                                else:
                                    # Play audio file
                                    self.play_audio(clicked_item.name, clicked_item.path)

            self.draw()
            clock.tick(60)

        pygame.quit()

if __name__ == "__main__":
    # Set your SuperCollider samples path here
    SAMPLES_PATH = r"PATH TO \SuperCollider\downloaded-quarks\Dirt-Samples"

    # Check if path exists
    if not os.path.exists(SAMPLES_PATH):
        print(f"Error: Path {SAMPLES_PATH} does not exist!")
        print("Please update the SAMPLES_PATH variable in the script.")
        sys.exit(1)

    browser = AudioBrowser(SAMPLES_PATH)
    browser.run()
