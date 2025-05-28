import tkinter as tk
from tkinter import ttk, messagebox, PhotoImage
import os
import threading
import queue
from collections import defaultdict
import sys # For determining executable path if bundled

# --- Configuration ---
# For bundled applications (PyInstaller), find resource files
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- Helper Functions ---
def human_readable_size(size, decimal_places=2):
    if size is None:
        return "N/A"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size < 1024.0 or unit == 'PB':
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"

# --- Main Application Class ---
class FileExplorerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("File Explorer Lite")
        self.root.geometry("900x600")

        # --- Internal State ---
        self.current_path = os.path.abspath(os.getcwd())
        self.history = [self.current_path]
        self.history_index = 0
        self.scan_queue = queue.Queue()
        self.scan_thread = None

        # --- Icons (simple built-in or specify paths if you have them) ---
        # Create tiny, simple icons if image files are not found
        try:
            # Attempt to load from files (if you create these image files)
            # self.folder_icon = PhotoImage(file=resource_path("icons/folder.png")) # Example
            # self.file_icon = PhotoImage(file=resource_path("icons/file.png")) # Example
            # self.up_icon = PhotoImage(file=resource_path("icons/up.png"))
            # self.back_icon = PhotoImage(file=resource_path("icons/back.png"))
            # self.forward_icon = PhotoImage(file=resource_path("icons/forward.png"))
            raise FileNotFoundError # Force fallback to placeholder icons for this example
        except Exception: # Fallback to creating simple icons
            self.folder_icon = self._create_placeholder_icon("gold", "folder")
            self.file_icon = self._create_placeholder_icon("lightgrey", "file")
            self.up_icon = self._create_placeholder_icon("lightblue", "↑")
            self.back_icon = self._create_placeholder_icon("lightgreen", "←")
            self.forward_icon = self._create_placeholder_icon("lightcoral", "→")


        # --- GUI Setup ---
        self._setup_ui()
        self.populate_treeview(self.current_path)
        self._update_nav_buttons_state()

    def _create_placeholder_icon(self, color, text=""):
        """Creates a simple PhotoImage icon."""
        img = PhotoImage(width=16, height=16)
        img.put(color, to=(0,0,15,15))
        if text: # Basic text rendering (very crude)
            if text == "folder":
                img.put("black", to=(2,2,13,4)) # Top flap
                img.put("black", to=(2,5,13,13)) # Body
                img.put(color, to=(3,6,12,12))  # Inner
            elif text == "file":
                img.put("black", to=(3,1,12,14)) # Rectangle
                img.put(color, to=(4,2,11,13)) # Inner
                img.put("black", to=(9,1,12,4)) # Folded corner
            else: # For arrows, just use the text on the button
                pass # Button will have text
        return img

    def _setup_ui(self):
        # --- Top Bar (Navigation & Path) ---
        top_frame = ttk.Frame(self.root, padding=5)
        top_frame.pack(fill=tk.X)

        self.back_button = ttk.Button(top_frame, image=self.back_icon, command=self.go_back)
        self.back_button.pack(side=tk.LEFT, padx=2)
        self.forward_button = ttk.Button(top_frame, image=self.forward_icon, command=self.go_forward)
        self.forward_button.pack(side=tk.LEFT, padx=2)
        self.up_button = ttk.Button(top_frame, image=self.up_icon, command=self.go_up)
        self.up_button.pack(side=tk.LEFT, padx=2)

        self.path_var = tk.StringVar(value=self.current_path)
        self.path_entry = ttk.Entry(top_frame, textvariable=self.path_var, font=("Segoe UI", 10))
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.path_entry.bind("<Return>", self.go_path_entry)

        go_button = ttk.Button(top_frame, text="Go", command=self.go_path_entry)
        go_button.pack(side=tk.LEFT, padx=2)

        # --- Main Area (Paned Window) ---
        main_paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # --- Left Pane (File/Folder Treeview) ---
        tree_frame = ttk.Frame(main_paned_window)
        self.tree = ttk.Treeview(tree_frame, columns=("type", "size"), show="headings", selectmode="browse")
        self.tree.heading("#0", text="Name") # Implicit first column if show="tree headings"
        self.tree.heading("type", text="Type")
        self.tree.heading("size", text="Size")
        self.tree.column("type", width=80, anchor="w")
        self.tree.column("size", width=100, anchor="e")
        # self.tree.column("#0", width=250) # If showing tree column

        # Add scrollbar to Treeview
        tree_scrollbar_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scrollbar_y.set)
        tree_scrollbar_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(xscrollcommand=tree_scrollbar_x.set)

        tree_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        tree_scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree.bind("<<TreeviewSelect>>", self.on_item_select)
        self.tree.bind("<Double-1>", self.on_item_double_click)

        main_paned_window.add(tree_frame, weight=2) # Give more weight to tree view

        # --- Right Pane (Information Display) ---
        info_frame = ttk.Labelframe(main_paned_window, text="Details", padding=10)
        self.info_text_widget = tk.Text(info_frame, wrap=tk.WORD, height=10, font=("Segoe UI", 9),
                                relief=tk.FLAT) # Removed background=info_frame.cget('background')
        self.info_text_widget.pack(fill=tk.BOTH, expand=True)
        self.info_text_widget.config(state=tk.DISABLED) # Read-only

        main_paned_window.add(info_frame, weight=1)

        # --- Status Bar ---
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=2)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def populate_treeview(self, path):
        self.tree.delete(*self.tree.get_children()) # Clear existing items
        self.current_path = os.path.abspath(path)
        self.path_var.set(self.current_path)
        self.status_var.set(f"Loading: {self.current_path}")
        self.root.update_idletasks() # Force update for status

        entries = []
        try:
            for item_name in os.listdir(path):
                item_path = os.path.join(path, item_name)
                try:
                    is_dir = os.path.isdir(item_path)
                    size = os.path.getsize(item_path) if not is_dir else None
                    entries.append((item_name, is_dir, size))
                except OSError: # Permission denied, symbolic link loop, etc.
                    entries.append((item_name, None, None)) # Mark as unknown

        except OSError as e:
            messagebox.showerror("Error", f"Could not access path: {path}\n{e}")
            if len(self.history) > 1 and self.history_index > 0:
                self.go_back(force_previous=True) # Try to go back to a valid path
            else:
                 # Fallback to user's home directory or CWD if everything fails
                fallback_path = os.path.expanduser("~")
                if not os.path.exists(fallback_path) or fallback_path == self.current_path:
                    fallback_path = os.getcwd()
                if fallback_path != self.current_path: # Avoid loop
                    self.navigate_to_path(fallback_path)
                else:
                    self.status_var.set("Error: Cannot access any valid path.")
            return

        # Sort: folders first, then files, all alphabetically
        entries.sort(key=lambda x: (not x[1] if x[1] is not None else True, x[0].lower()))

        for name, is_dir, size in entries:
            icon = self.folder_icon if is_dir else self.file_icon
            item_type = "Folder" if is_dir else (os.path.splitext(name)[1] or "File").upper()
            size_str = human_readable_size(size) if size is not None else ""
            
            # Use name for the implicit first column's text if show="tree headings"
            # If show="tree", then text=name for the tree column
            self.tree.insert("", tk.END, text=name, image=icon, values=(name, item_type, size_str))
        
        if not self.tree.get_children():
            self.tree.insert("", tk.END, values=("(empty)", "", ""))

        self.status_var.set("Ready")

    def navigate_to_path(self, new_path, add_to_history=True):
        abs_new_path = os.path.abspath(new_path)
        if os.path.isdir(abs_new_path):
            self.current_path = abs_new_path
            self.populate_treeview(self.current_path)
            self.clear_info_display()

            if add_to_history:
                # If navigating to a new path not via back/forward, clear future history
                if self.history_index < len(self.history) - 1:
                    self.history = self.history[:self.history_index + 1]
                
                # Add to history only if it's different from the last entry
                if not self.history or self.history[-1] != self.current_path:
                    self.history.append(self.current_path)
                self.history_index = len(self.history) - 1
            
            self._update_nav_buttons_state()
        else:
            messagebox.showerror("Error", f"Path not found or is not a directory: {abs_new_path}")
            self.path_var.set(self.current_path) # Reset entry to current valid path

    def on_item_select(self, event=None):
        selected_items = self.tree.selection()
        if not selected_items:
            self.clear_info_display()
            return

        selected_item_id = selected_items[0]
        item_values = self.tree.item(selected_item_id, "values")
        item_name = item_values[0] # Name is now in values
        
        if item_name == "(empty)":
            self.clear_info_display()
            return

        full_path = os.path.join(self.current_path, item_name)

        if os.path.isdir(full_path):
            self.status_var.set(f"Scanning folder: {item_name}...")
            self.display_info(f"Name: {item_name}\nType: Folder\n\nScanning contents recursively...\nPlease wait.")
            # Start threaded scan
            if self.scan_thread and self.scan_thread.is_alive():
                # A scan is already in progress, maybe inform user or queue?
                # For simplicity, we'll just let the new one start (old one will finish and be ignored)
                pass
            self.scan_thread = threading.Thread(target=self._scan_folder_worker, args=(full_path, item_name), daemon=True)
            self.scan_thread.start()
            self.root.after(100, self._check_scan_queue)
        elif os.path.isfile(full_path):
            self.status_var.set(f"Selected file: {item_name}")
            try:
                size = os.path.getsize(full_path)
                file_type = (os.path.splitext(item_name)[1] or "File").upper()
                info = f"Name: {item_name}\n"
                info += f"Type: {file_type}\n"
                info += f"Size: {human_readable_size(size)} ({size} bytes)"
                self.display_info(info)
            except OSError as e:
                self.display_info(f"Name: {item_name}\nError: Could not access file properties.\n{e}")
        else:
            self.display_info(f"Name: {item_name}\nType: Unknown or Inaccessible")
            self.status_var.set(f"Selected: {item_name} (Unknown/Inaccessible)")

    def _scan_folder_worker(self, folder_path, folder_name_display):
        total_size = 0
        file_count = 0
        folder_count = 0 # Not including the top folder_path itself initially
        type_counts = defaultdict(int)
        
        try:
            for root_dir, dirs, files in os.walk(folder_path, topdown=True, onerror=None):
                # onerror=None skips directories that can't be accessed
                folder_count += len(dirs)
                for file_name in files:
                    file_path = os.path.join(root_dir, file_name)
                    try:
                        if not os.path.islink(file_path): # Avoid issues with symlinks if getsize fails
                            total_size += os.path.getsize(file_path)
                        file_count += 1
                        ext = (os.path.splitext(file_name)[1] or ".no_ext").lower()
                        type_counts[ext] += 1
                    except OSError:
                        # Skip files that can't be accessed (e.g., permission denied, broken symlink)
                        pass
            self.scan_queue.put({
                "name": folder_name_display,
                "total_size": total_size,
                "file_count": file_count,
                "folder_count": folder_count,
                "type_counts": type_counts,
                "error": None
            })
        except Exception as e:
            self.scan_queue.put({"name": folder_name_display, "error": e})

    def _check_scan_queue(self):
        try:
            result = self.scan_queue.get_nowait()
            if result.get("error"):
                info = f"Name: {result['name']}\nType: Folder\n\nError scanning contents:\n{result['error']}"
                self.status_var.set(f"Error scanning {result['name']}")
            else:
                info = f"Name: {result['name']}\nType: Folder\n\n"
                info += f"Total Size (Contents): {human_readable_size(result['total_size'])}\n"
                info += f"Total Files: {result['file_count']}\n"
                info += f"Total Subfolders: {result['folder_count']}\n\n"
                
                if result['type_counts']:
                    info += "Document Types (by count):\n"
                    sorted_types = sorted(result['type_counts'].items(), key=lambda item: item[1], reverse=True)
                    for ext, count in sorted_types[:10]: # Display top 10 types
                        info += f"  {ext if ext else '(no ext)'}: {count}\n"
                    if len(sorted_types) > 10:
                        info += f"  ...and {len(sorted_types) - 10} more types.\n"
                else:
                    info += "No files found in contents.\n"
                self.status_var.set(f"Scan complete for {result['name']}")

            self.display_info(info)

        except queue.Empty:
            if self.scan_thread and self.scan_thread.is_alive():
                self.root.after(100, self._check_scan_queue) # Reschedule check
            else: # Thread finished but queue was empty or thread died unexpectedly
                if not self.info_text_widget.get("1.0", tk.END).strip().endswith("Please wait."):
                    # Only set to ready if we weren't already displaying results
                    self.status_var.set("Ready")

    def on_item_double_click(self, event=None):
        selected_items = self.tree.selection()
        if not selected_items:
            return

        selected_item_id = selected_items[0]
        item_values = self.tree.item(selected_item_id, "values")
        item_name = item_values[0]

        if item_name == "(empty)": return

        potential_path = os.path.join(self.current_path, item_name)
        if os.path.isdir(potential_path):
            self.navigate_to_path(potential_path)

    def display_info(self, text):
        self.info_text_widget.config(state=tk.NORMAL)
        self.info_text_widget.delete("1.0", tk.END)
        self.info_text_widget.insert(tk.END, text)
        self.info_text_widget.config(state=tk.DISABLED)

    def clear_info_display(self):
        self.display_info("")

    def go_up(self):
        parent_path = os.path.dirname(self.current_path)
        if parent_path != self.current_path: # Check to prevent getting stuck at root
            self.navigate_to_path(parent_path)

    def go_back(self, force_previous=False):
        if self.history_index > 0:
            self.history_index -= 1
            self.navigate_to_path(self.history[self.history_index], add_to_history=False)
        elif force_previous and self.history: # Used in error recovery
             self.navigate_to_path(self.history[-1], add_to_history=False)

    def go_forward(self):
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.navigate_to_path(self.history[self.history_index], add_to_history=False)

    def go_path_entry(self, event=None):
        path_from_entry = self.path_var.get()
        self.navigate_to_path(path_from_entry)

    def _update_nav_buttons_state(self):
        self.back_button.config(state=tk.NORMAL if self.history_index > 0 else tk.DISABLED)
        self.forward_button.config(state=tk.NORMAL if self.history_index < len(self.history) - 1 else tk.DISABLED)
        parent_path = os.path.dirname(self.current_path)
        self.up_button.config(state=tk.NORMAL if parent_path != self.current_path else tk.DISABLED)


# --- Main Execution ---
if __name__ == "__main__":
    root = tk.Tk()
    app = FileExplorerApp(root)
    root.mainloop()