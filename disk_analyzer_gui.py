#!/usr/bin/env python3
"""
Disk Analyzer GUI - Beautiful Cross-Platform Wizard Interface
Uses CustomTkinter for modern UI components
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import platform
import threading
import queue
import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

# Import our core analyzer
from disk_analyzer_core import DiskAnalyzerCore, MB, GB

# Configure CustomTkinter
ctk.set_appearance_mode("dark")  # Default to dark mode
ctk.set_default_color_theme("blue")

class WizardFrame(ctk.CTkFrame):
    """Base class for wizard screens"""
    def __init__(self, parent, wizard):
        super().__init__(parent, corner_radius=0, fg_color="transparent")
        self.wizard = wizard
        self.grid(row=0, column=0, sticky="nsew")
        
    def on_show(self):
        """Called when this screen is shown"""
        pass
        
    def validate(self) -> bool:
        """Validate before moving to next screen"""
        return True

class WelcomeScreen(WizardFrame):
    """Welcome screen with mode selection"""
    def __init__(self, parent, wizard):
        super().__init__(parent, wizard)
        
        # Create gradient-like background effect
        self.configure(fg_color=("gray90", "gray10"))
        
        # Title with large font
        title = ctk.CTkLabel(
            self,
            text="Disk Space Analyzer",
            font=ctk.CTkFont(size=48, weight="bold")
        )
        title.pack(pady=(100, 20))
        
        # Subtitle
        subtitle = ctk.CTkLabel(
            self,
            text="Analyze and optimize your disk space across Windows, macOS, and Linux",
            font=ctk.CTkFont(size=16),
            text_color=("gray20", "gray80")
        )
        subtitle.pack(pady=(0, 50))
        
        # System info
        system_info = f"Detected System: {platform.system()} {platform.release()}"
        system_label = ctk.CTkLabel(
            self,
            text=system_info,
            font=ctk.CTkFont(size=14),
            text_color=("gray30", "gray70")
        )
        system_label.pack(pady=(0, 30))
        
        # Mode selection frame
        mode_frame = ctk.CTkFrame(self, fg_color="transparent")
        mode_frame.pack(pady=20)
        
        # Quick scan button
        self.quick_button = ctk.CTkButton(
            mode_frame,
            text="Quick Scan\n(Files > 50MB)",
            width=200,
            height=100,
            font=ctk.CTkFont(size=18, weight="bold"),
            command=lambda: self.select_mode("quick"),
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40")
        )
        self.quick_button.grid(row=0, column=0, padx=20, pady=10)
        
        # Full analysis button
        self.full_button = ctk.CTkButton(
            mode_frame,
            text="Full Analysis\n(All files > 10MB)",
            width=200,
            height=100,
            font=ctk.CTkFont(size=18, weight="bold"),
            command=lambda: self.select_mode("full"),
            fg_color=("#3B8ED0", "#1F6AA5"),
            hover_color=("#36719F", "#144870")
        )
        self.full_button.grid(row=0, column=1, padx=20, pady=10)
        
        # Theme toggle
        self.theme_switch = ctk.CTkSwitch(
            self,
            text="Dark Mode",
            command=self.toggle_theme,
            onvalue="dark",
            offvalue="light"
        )
        self.theme_switch.pack(side="bottom", pady=20)
        self.theme_switch.select()  # Default to dark mode
        
    def select_mode(self, mode: str):
        """Select scan mode and proceed"""
        self.wizard.scan_mode = mode
        self.wizard.min_size_mb = 50 if mode == "quick" else 10
        self.wizard.next_screen()
        
    def toggle_theme(self):
        """Toggle between light and dark theme"""
        new_mode = self.theme_switch.get()
        ctk.set_appearance_mode(new_mode)

class DriveSelectionScreen(WizardFrame):
    """Drive/Path selection screen"""
    def __init__(self, parent, wizard):
        super().__init__(parent, wizard)
        
        # Title
        title = ctk.CTkLabel(
            self,
            text="Select Drives or Paths to Analyze",
            font=ctk.CTkFont(size=32, weight="bold")
        )
        title.pack(pady=(50, 30))
        
        # Main content frame
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=50, pady=20)
        
        if platform.system() == "Windows":
            self.create_windows_drive_selection(content_frame)
        else:
            self.create_unix_path_selection(content_frame)
            
        # Navigation buttons
        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.pack(side="bottom", pady=20)
        
        ctk.CTkButton(
            nav_frame,
            text="Back",
            command=self.wizard.prev_screen,
            width=120,
            fg_color="gray50",
            hover_color="gray40"
        ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            nav_frame,
            text="Next",
            command=self.wizard.next_screen,
            width=120
        ).pack(side="left", padx=10)
        
    def create_windows_drive_selection(self, parent):
        """Create Windows drive selection UI"""
        # Get available drives
        analyzer = DiskAnalyzerCore("C:\\")
        drives = analyzer.get_all_drives()
        
        # Scrollable frame for drives
        scroll_frame = ctk.CTkScrollableFrame(parent, height=300)
        scroll_frame.pack(fill="both", expand=True, pady=10)
        
        self.drive_vars = {}
        self.wizard.selected_paths = []
        
        for drive in drives:
            # Drive frame
            drive_frame = ctk.CTkFrame(scroll_frame)
            drive_frame.pack(fill="x", pady=5, padx=10)
            
            # Checkbox
            var = ctk.BooleanVar(value=drive['letter'] == 'C')
            self.drive_vars[drive['path']] = var
            
            checkbox = ctk.CTkCheckBox(
                drive_frame,
                text=f"Drive {drive['letter']}:",
                variable=var,
                font=ctk.CTkFont(size=16, weight="bold"),
                command=lambda p=drive['path']: self.toggle_drive(p)
            )
            checkbox.pack(side="left", padx=10)
            
            # Usage info
            usage_text = f"{self.format_size(drive['used'])} / {self.format_size(drive['total'])} ({drive['percent']:.1f}%)"
            usage_label = ctk.CTkLabel(
                drive_frame,
                text=usage_text,
                font=ctk.CTkFont(size=14)
            )
            usage_label.pack(side="left", padx=20)
            
            # Progress bar
            progress = ctk.CTkProgressBar(drive_frame, width=200)
            progress.set(drive['percent'] / 100)
            progress.pack(side="left", padx=10)
            
        # Custom path option
        custom_frame = ctk.CTkFrame(parent)
        custom_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            custom_frame,
            text="Or select a custom path:",
            font=ctk.CTkFont(size=14)
        ).pack(side="left", padx=10)
        
        self.custom_path_var = ctk.StringVar()
        self.custom_entry = ctk.CTkEntry(
            custom_frame,
            textvariable=self.custom_path_var,
            width=300
        )
        self.custom_entry.pack(side="left", padx=10)
        
        ctk.CTkButton(
            custom_frame,
            text="Browse",
            command=self.browse_folder,
            width=100
        ).pack(side="left", padx=5)
        
    def create_unix_path_selection(self, parent):
        """Create Unix path selection UI"""
        # Common locations
        locations = [
            ("Home Directory", str(Path.home())),
            ("Root Directory", "/"),
            ("Downloads", str(Path.home() / "Downloads")),
            ("Documents", str(Path.home() / "Documents")),
        ]
        
        if platform.system() == "Darwin":  # macOS
            locations.append(("Applications", "/Applications"))
            
        # Scrollable frame
        scroll_frame = ctk.CTkScrollableFrame(parent, height=300)
        scroll_frame.pack(fill="both", expand=True, pady=10)
        
        self.path_vars = {}
        self.wizard.selected_paths = []
        
        for name, path in locations:
            if Path(path).exists():
                # Path frame
                path_frame = ctk.CTkFrame(scroll_frame)
                path_frame.pack(fill="x", pady=5, padx=10)
                
                # Checkbox
                var = ctk.BooleanVar(value=(name == "Home Directory"))
                self.path_vars[path] = var
                
                checkbox = ctk.CTkCheckBox(
                    path_frame,
                    text=name,
                    variable=var,
                    font=ctk.CTkFont(size=16),
                    command=lambda p=path: self.toggle_path(p)
                )
                checkbox.pack(side="left", padx=10)
                
                # Path label
                path_label = ctk.CTkLabel(
                    path_frame,
                    text=path,
                    font=ctk.CTkFont(size=12),
                    text_color=("gray30", "gray70")
                )
                path_label.pack(side="left", padx=20)
                
        # Custom path option
        custom_frame = ctk.CTkFrame(parent)
        custom_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            custom_frame,
            text="Custom path:",
            font=ctk.CTkFont(size=14)
        ).pack(side="left", padx=10)
        
        self.custom_path_var = ctk.StringVar()
        self.custom_entry = ctk.CTkEntry(
            custom_frame,
            textvariable=self.custom_path_var,
            width=400
        )
        self.custom_entry.pack(side="left", padx=10)
        
        ctk.CTkButton(
            custom_frame,
            text="Browse",
            command=self.browse_folder,
            width=100
        ).pack(side="left", padx=5)
        
    def toggle_drive(self, path: str):
        """Toggle drive selection"""
        if self.drive_vars[path].get():
            if path not in self.wizard.selected_paths:
                self.wizard.selected_paths.append(path)
        else:
            if path in self.wizard.selected_paths:
                self.wizard.selected_paths.remove(path)
                
    def toggle_path(self, path: str):
        """Toggle path selection"""
        if self.path_vars[path].get():
            if path not in self.wizard.selected_paths:
                self.wizard.selected_paths.append(path)
        else:
            if path in self.wizard.selected_paths:
                self.wizard.selected_paths.remove(path)
                
    def browse_folder(self):
        """Browse for custom folder"""
        folder = filedialog.askdirectory()
        if folder:
            self.custom_path_var.set(folder)
            if folder not in self.wizard.selected_paths:
                self.wizard.selected_paths.append(folder)
                
    def format_size(self, size: int) -> str:
        """Format size in human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"
        
    def validate(self) -> bool:
        """Validate selection"""
        # Check custom path
        custom_path = self.custom_path_var.get()
        if custom_path and custom_path not in self.wizard.selected_paths:
            self.wizard.selected_paths.append(custom_path)
            
        if not self.wizard.selected_paths:
            messagebox.showwarning(
                "No Selection",
                "Please select at least one drive or path to analyze."
            )
            return False
        return True

class AnalysisOptionsScreen(WizardFrame):
    """Analysis options configuration"""
    def __init__(self, parent, wizard):
        super().__init__(parent, wizard)
        
        # Title
        title = ctk.CTkLabel(
            self,
            text="Configure Analysis Options",
            font=ctk.CTkFont(size=32, weight="bold")
        )
        title.pack(pady=(50, 30))
        
        # Options frame
        options_frame = ctk.CTkFrame(self)
        options_frame.pack(expand=True, padx=50, pady=20)
        
        # Minimum file size
        size_label = ctk.CTkLabel(
            options_frame,
            text="Minimum file size to report:",
            font=ctk.CTkFont(size=16)
        )
        size_label.grid(row=0, column=0, padx=20, pady=20, sticky="w")
        
        self.size_var = ctk.DoubleVar(value=self.wizard.min_size_mb)
        self.size_label_value = ctk.CTkLabel(
            options_frame,
            text=f"{self.wizard.min_size_mb} MB",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.size_label_value.grid(row=0, column=2, padx=20, pady=20)
        
        self.size_slider = ctk.CTkSlider(
            options_frame,
            from_=1,
            to=1000,
            variable=self.size_var,
            command=self.update_size_label,
            width=300
        )
        self.size_slider.grid(row=0, column=1, padx=20, pady=20)
        
        # Categories to analyze
        cat_label = ctk.CTkLabel(
            options_frame,
            text="Categories to analyze:",
            font=ctk.CTkFont(size=16)
        )
        cat_label.grid(row=1, column=0, padx=20, pady=(30, 10), sticky="nw")
        
        # Category checkboxes
        categories_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        categories_frame.grid(row=1, column=1, columnspan=2, padx=20, pady=(30, 10), sticky="w")
        
        self.category_vars = {}
        categories = [
            ("System Cache", True),
            ("Development Files", True),
            ("Docker Resources", True),
            ("Large Media Files", True),
            ("Old Downloads", True),
            ("Temporary Files", True)
        ]
        
        for i, (cat, default) in enumerate(categories):
            var = ctk.BooleanVar(value=default)
            self.category_vars[cat] = var
            
            checkbox = ctk.CTkCheckBox(
                categories_frame,
                text=cat,
                variable=var,
                font=ctk.CTkFont(size=14)
            )
            checkbox.grid(row=i//2, column=i%2, padx=20, pady=5, sticky="w")
            
        # Export options
        export_label = ctk.CTkLabel(
            options_frame,
            text="Export options:",
            font=ctk.CTkFont(size=16)
        )
        export_label.grid(row=3, column=0, padx=20, pady=(30, 10), sticky="nw")
        
        export_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        export_frame.grid(row=3, column=1, columnspan=2, padx=20, pady=(30, 10), sticky="w")
        
        self.export_html = ctk.BooleanVar(value=True)
        self.export_json = ctk.BooleanVar(value=False)
        self.export_csv = ctk.BooleanVar(value=False)
        
        ctk.CTkCheckBox(
            export_frame,
            text="HTML Report",
            variable=self.export_html,
            font=ctk.CTkFont(size=14)
        ).grid(row=0, column=0, padx=20, pady=5, sticky="w")
        
        ctk.CTkCheckBox(
            export_frame,
            text="JSON Data",
            variable=self.export_json,
            font=ctk.CTkFont(size=14)
        ).grid(row=0, column=1, padx=20, pady=5, sticky="w")
        
        ctk.CTkCheckBox(
            export_frame,
            text="CSV Summary",
            variable=self.export_csv,
            font=ctk.CTkFont(size=14)
        ).grid(row=0, column=2, padx=20, pady=5, sticky="w")
        
        # Navigation
        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.pack(side="bottom", pady=20)
        
        ctk.CTkButton(
            nav_frame,
            text="Back",
            command=self.wizard.prev_screen,
            width=120,
            fg_color="gray50",
            hover_color="gray40"
        ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            nav_frame,
            text="Start Analysis",
            command=self.start_analysis,
            width=150,
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(side="left", padx=10)
        
    def update_size_label(self, value):
        """Update size label with slider value"""
        self.wizard.min_size_mb = int(value)
        self.size_label_value.configure(text=f"{int(value)} MB")
        
    def start_analysis(self):
        """Save options and start analysis"""
        self.wizard.export_options = {
            'html': self.export_html.get(),
            'json': self.export_json.get(),
            'csv': self.export_csv.get()
        }
        self.wizard.categories = {k: v.get() for k, v in self.category_vars.items()}
        self.wizard.next_screen()

class AnalysisProgressScreen(WizardFrame):
    """Analysis progress screen with real-time updates"""
    def __init__(self, parent, wizard):
        super().__init__(parent, wizard)
        
        # Title
        title = ctk.CTkLabel(
            self,
            text="Analyzing Disk Space...",
            font=ctk.CTkFont(size=32, weight="bold")
        )
        title.pack(pady=(50, 30))
        
        # Progress frame
        progress_frame = ctk.CTkFrame(self)
        progress_frame.pack(expand=True, padx=50, pady=20)
        
        # Circular progress (using canvas)
        self.canvas = tk.Canvas(
            progress_frame,
            width=200,
            height=200,
            bg=ctk.ThemeManager.theme["CTkFrame"]["fg_color"][1 if ctk.get_appearance_mode() == "Dark" else 0],
            highlightthickness=0
        )
        self.canvas.pack(pady=20)
        
        # Progress bar
        self.progress = ctk.CTkProgressBar(progress_frame, width=400)
        self.progress.pack(pady=20)
        self.progress.set(0)
        
        # Status label
        self.status_label = ctk.CTkLabel(
            progress_frame,
            text="Initializing...",
            font=ctk.CTkFont(size=16)
        )
        self.status_label.pack(pady=10)
        
        # Current file label
        self.file_label = ctk.CTkLabel(
            progress_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70")
        )
        self.file_label.pack(pady=5)
        
        # Statistics frame
        stats_frame = ctk.CTkFrame(progress_frame, fg_color="transparent")
        stats_frame.pack(pady=20)
        
        # Files scanned
        self.files_label = ctk.CTkLabel(
            stats_frame,
            text="Files scanned: 0",
            font=ctk.CTkFont(size=14)
        )
        self.files_label.grid(row=0, column=0, padx=20, pady=5)
        
        # Large files found
        self.large_files_label = ctk.CTkLabel(
            stats_frame,
            text="Large files: 0",
            font=ctk.CTkFont(size=14)
        )
        self.large_files_label.grid(row=0, column=1, padx=20, pady=5)
        
        # Errors
        self.errors_label = ctk.CTkLabel(
            stats_frame,
            text="Errors: 0",
            font=ctk.CTkFont(size=14)
        )
        self.errors_label.grid(row=0, column=2, padx=20, pady=5)
        
        # Cancel button
        self.cancel_button = ctk.CTkButton(
            self,
            text="Cancel",
            command=self.cancel_analysis,
            width=120,
            fg_color="red",
            hover_color="darkred"
        )
        self.cancel_button.pack(side="bottom", pady=20)
        
        # Queue for thread communication
        self.queue = queue.Queue()
        self.analysis_thread = None
        
    def on_show(self):
        """Start analysis when screen is shown"""
        self.start_analysis()
        
    def start_analysis(self):
        """Start analysis in background thread"""
        self.wizard.results = {}
        self.analysis_thread = threading.Thread(target=self.run_analysis)
        self.analysis_thread.daemon = True
        self.analysis_thread.start()
        
        # Start checking queue
        self.after(100, self.check_queue)
        
    def run_analysis(self):
        """Run analysis in background"""
        try:
            all_results = []
            total_paths = len(self.wizard.selected_paths)
            
            for idx, path in enumerate(self.wizard.selected_paths):
                if hasattr(self, 'cancel_flag') and self.cancel_flag:
                    break
                    
                # Create analyzer with progress callback
                analyzer = DiskAnalyzerCore(
                    path,
                    self.wizard.min_size_mb,
                    progress_callback=lambda info: self.queue.put(('progress', info))
                )
                
                # Update overall progress
                overall_progress = idx / total_paths
                self.queue.put(('overall', {
                    'path': path,
                    'progress': overall_progress,
                    'current': idx + 1,
                    'total': total_paths
                }))
                
                # Run analysis
                result = analyzer.analyze()
                
                if result:
                    report = analyzer.generate_report()
                    all_results.append({
                        'path': path,
                        'analyzer': analyzer,
                        'report': report
                    })
                    
            self.queue.put(('complete', all_results))
            
        except Exception as e:
            self.queue.put(('error', str(e)))
            
    def check_queue(self):
        """Check queue for updates"""
        try:
            while True:
                msg_type, data = self.queue.get_nowait()
                
                if msg_type == 'progress':
                    self.update_progress(data)
                elif msg_type == 'overall':
                    self.update_overall_progress(data)
                elif msg_type == 'complete':
                    self.analysis_complete(data)
                    return
                elif msg_type == 'error':
                    self.analysis_error(data)
                    return
                    
        except queue.Empty:
            pass
            
        # Continue checking
        self.after(100, self.check_queue)
        
    def update_progress(self, info: Dict):
        """Update progress display"""
        if 'percent' in info and info['percent'] is not None:
            self.progress.set(info['percent'] / 100)
            self.draw_circular_progress(info['percent'])
            
        if 'message' in info:
            self.status_label.configure(text=info['message'])
            
        if 'current_file' in info and info['current_file']:
            # Truncate long paths
            file_path = info['current_file']
            if len(file_path) > 60:
                file_path = "..." + file_path[-57:]
            self.file_label.configure(text=file_path)
            
        # Update statistics
        self.files_label.configure(text=f"Files scanned: {info.get('files_scanned', 0):,}")
        self.large_files_label.configure(text=f"Large files: {info.get('large_files_found', 0):,}")
        self.errors_label.configure(text=f"Errors: {info.get('errors', 0)}")
        
    def update_overall_progress(self, info: Dict):
        """Update overall progress for multiple paths"""
        status = f"Analyzing {info['current']} of {info['total']}: {Path(info['path']).name}"
        self.status_label.configure(text=status)
        
    def draw_circular_progress(self, percent: float):
        """Draw circular progress indicator"""
        self.canvas.delete("all")
        
        # Colors
        bg_color = "#2b2b2b" if ctk.get_appearance_mode() == "Dark" else "#e0e0e0"
        fg_color = "#3B8ED0" if ctk.get_appearance_mode() == "Dark" else "#1F6AA5"
        
        # Draw background circle
        self.canvas.create_arc(
            20, 20, 180, 180,
            start=0, extent=360,
            outline=bg_color, width=20,
            style="arc"
        )
        
        # Draw progress arc
        if percent > 0:
            self.canvas.create_arc(
                20, 20, 180, 180,
                start=90, extent=-360 * (percent / 100),
                outline=fg_color, width=20,
                style="arc"
            )
            
        # Draw percentage text
        self.canvas.create_text(
            100, 100,
            text=f"{int(percent)}%",
            fill=fg_color,
            font=("Arial", 24, "bold")
        )
        
    def cancel_analysis(self):
        """Cancel ongoing analysis"""
        self.cancel_flag = True
        if hasattr(self.wizard.current_analyzer, 'cancel_analysis'):
            self.wizard.current_analyzer.cancel_analysis()
        self.cancel_button.configure(text="Cancelling...")
        self.cancel_button.configure(state="disabled")
        
    def analysis_complete(self, results: List[Dict]):
        """Analysis completed successfully"""
        self.wizard.analysis_results = results
        self.wizard.next_screen()
        
    def analysis_error(self, error: str):
        """Handle analysis error"""
        messagebox.showerror("Analysis Error", f"An error occurred during analysis:\n\n{error}")
        self.wizard.prev_screen()

class ResultsDashboardScreen(WizardFrame):
    """Results dashboard with tabs"""
    def __init__(self, parent, wizard):
        super().__init__(parent, wizard)
        
        # Title
        title = ctk.CTkLabel(
            self,
            text="Analysis Results",
            font=ctk.CTkFont(size=32, weight="bold")
        )
        title.pack(pady=(30, 20))
        
        # Create tabview
        self.tabview = ctk.CTkTabview(self, width=900, height=500)
        self.tabview.pack(expand=True, fill="both", padx=20, pady=10)
        
        # Add tabs
        self.tabview.add("Overview")
        self.tabview.add("Recommendations")
        self.tabview.add("Details")
        
        # Navigation frame
        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.pack(side="bottom", pady=20)
        
        ctk.CTkButton(
            nav_frame,
            text="New Analysis",
            command=self.new_analysis,
            width=120,
            fg_color="gray50",
            hover_color="gray40"
        ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            nav_frame,
            text="Export Reports",
            command=self.export_reports,
            width=120
        ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            nav_frame,
            text="Exit",
            command=self.wizard.quit,
            width=120,
            fg_color="red",
            hover_color="darkred"
        ).pack(side="left", padx=10)
        
    def on_show(self):
        """Populate results when shown"""
        self.populate_overview()
        self.populate_recommendations()
        self.populate_details()
        
    def populate_overview(self):
        """Populate overview tab"""
        tab = self.tabview.tab("Overview")
        
        # Clear existing content
        for widget in tab.winfo_children():
            widget.destroy()
            
        # Create summary frame
        summary_frame = ctk.CTkFrame(tab)
        summary_frame.pack(fill="x", padx=10, pady=10)
        
        # Calculate totals
        total_size = 0
        total_files = 0
        total_large_files = 0
        
        for result in self.wizard.analysis_results:
            report = result['report']
            total_size += report['summary']['total_size']
            total_files += report['summary']['files_scanned']
            total_large_files += report['summary']['large_files_count']
            
        # Display summary
        summary_text = f"""
Total Space Analyzed: {self.format_size(total_size)}
Files Scanned: {total_files:,}
Large Files Found: {total_large_files:,}
Paths Analyzed: {len(self.wizard.analysis_results)}
        """
        
        summary_label = ctk.CTkLabel(
            summary_frame,
            text=summary_text.strip(),
            font=ctk.CTkFont(size=16),
            justify="left"
        )
        summary_label.pack(padx=20, pady=20)
        
        # Create chart frame
        chart_frame = ctk.CTkFrame(tab)
        chart_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create matplotlib figure
        fig = Figure(figsize=(10, 6), dpi=80)
        ax = fig.add_subplot(111)
        
        # Prepare data for pie chart
        categories = {}
        for result in self.wizard.analysis_results:
            analyzer = result['analyzer']
            for ext, data in analyzer.file_type_stats.items():
                if ext not in categories:
                    categories[ext] = 0
                categories[ext] += data['size']
                
        # Get top 10 categories
        sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:10]
        
        if sorted_cats:
            labels = [cat[0] if cat[0] else 'No Extension' for cat in sorted_cats]
            sizes = [cat[1] for cat in sorted_cats]
            
            # Create pie chart
            colors = plt.cm.Set3(range(len(labels)))
            ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
            ax.set_title('Disk Usage by File Type', fontsize=16, fontweight='bold')
            
        # Embed chart in tkinter
        canvas = FigureCanvasTkAgg(fig, master=chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        
    def populate_recommendations(self):
        """Populate recommendations tab"""
        tab = self.tabview.tab("Recommendations")
        
        # Clear existing content
        for widget in tab.winfo_children():
            widget.destroy()
            
        # Create scrollable frame
        scroll_frame = ctk.CTkScrollableFrame(tab, height=400)
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Collect all recommendations
        all_recommendations = []
        for result in self.wizard.analysis_results:
            recommendations = result['report'].get('recommendations', [])
            for rec in recommendations:
                rec['path'] = result['path']
                all_recommendations.append(rec)
                
        # Sort by space recoverable
        all_recommendations.sort(key=lambda x: x.get('space', 0), reverse=True)
        
        # Display recommendations
        for idx, rec in enumerate(all_recommendations[:20]):  # Top 20
            rec_frame = ctk.CTkFrame(scroll_frame)
            rec_frame.pack(fill="x", padx=5, pady=5)
            
            # Priority color
            priority_colors = {
                'Alta': 'red',
                'Media': 'orange',
                'Baja': 'green'
            }
            priority_color = priority_colors.get(rec.get('priority', 'Media'), 'gray')
            
            # Priority label
            priority_label = ctk.CTkLabel(
                rec_frame,
                text=rec.get('priority', 'Media'),
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=priority_color,
                width=60
            )
            priority_label.pack(side="left", padx=10)
            
            # Description
            desc_text = f"{rec.get('type', 'Unknown')}: {rec.get('description', '')}"
            desc_label = ctk.CTkLabel(
                rec_frame,
                text=desc_text,
                font=ctk.CTkFont(size=14),
                anchor="w"
            )
            desc_label.pack(side="left", fill="x", expand=True, padx=10)
            
            # Space recoverable
            space_label = ctk.CTkLabel(
                rec_frame,
                text=self.format_size(rec.get('space', 0)),
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="green",
                width=100
            )
            space_label.pack(side="right", padx=10)
            
            # Action button
            if rec.get('command'):
                action_button = ctk.CTkButton(
                    rec_frame,
                    text="Preview",
                    command=lambda cmd=rec['command']: self.preview_cleanup(cmd),
                    width=80,
                    height=28
                )
                action_button.pack(side="right", padx=5)
                
    def populate_details(self):
        """Populate details tab"""
        tab = self.tabview.tab("Details")
        
        # Clear existing content
        for widget in tab.winfo_children():
            widget.destroy()
            
        # Create treeview frame
        tree_frame = ctk.CTkFrame(tab)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create search frame
        search_frame = ctk.CTkFrame(tree_frame)
        search_frame.pack(fill="x", padx=5, pady=5)
        
        ctk.CTkLabel(
            search_frame,
            text="Search:",
            font=ctk.CTkFont(size=14)
        ).pack(side="left", padx=5)
        
        self.search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(
            search_frame,
            textvariable=self.search_var,
            width=300
        )
        search_entry.pack(side="left", padx=5)
        
        # Create text widget for file list (simpler than treeview)
        self.details_text = ctk.CTkTextbox(tree_frame, height=300)
        self.details_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Populate with large files
        all_files = []
        for result in self.wizard.analysis_results:
            for file in result['report'].get('large_files', []):
                file['base_path'] = result['path']
                all_files.append(file)
                
        # Sort by size
        all_files.sort(key=lambda x: x['size'], reverse=True)
        
        # Display files
        self.details_text.insert("1.0", "Top Large Files:\n\n")
        for idx, file in enumerate(all_files[:100]):  # Top 100
            file_text = f"{idx+1}. {self.format_size(file['size']):>10} - {file['path']}\n"
            self.details_text.insert("end", file_text)
            
        self.details_text.configure(state="disabled")
        
        # Bind search
        search_entry.bind('<KeyRelease>', self.search_files)
        
    def format_size(self, size: int) -> str:
        """Format size in human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"
        
    def preview_cleanup(self, command: str):
        """Preview cleanup command"""
        messagebox.showinfo(
            "Cleanup Command Preview",
            f"Command that would be executed:\n\n{command}\n\n"
            "To execute cleanup commands, use the command-line interface."
        )
        
    def search_files(self, event):
        """Search files in details"""
        # This is a placeholder - implement actual search functionality
        pass
        
    def new_analysis(self):
        """Start new analysis"""
        self.wizard.show_screen(0)
        
    def export_reports(self):
        """Export analysis reports"""
        # Ask for directory
        export_dir = filedialog.askdirectory(title="Select Export Directory")
        if not export_dir:
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Export based on selected options
        if self.wizard.export_options.get('html', True):
            # Generate HTML report using the original analyzer's method
            html_file = Path(export_dir) / f"disk_analysis_{timestamp}.html"
            # TODO: Call original HTML generation method
            
        if self.wizard.export_options.get('json', False):
            json_file = Path(export_dir) / f"disk_analysis_{timestamp}.json"
            with open(json_file, 'w') as f:
                json.dump([r['report'] for r in self.wizard.analysis_results], f, indent=2)
                
        messagebox.showinfo(
            "Export Complete",
            f"Reports exported to:\n{export_dir}"
        )

class DiskAnalyzerWizard(ctk.CTk):
    """Main wizard application"""
    def __init__(self):
        super().__init__()
        
        # Window setup
        self.title("Disk Space Analyzer")
        self.geometry("1000x700")
        self.minsize(800, 600)
        
        # Center window
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        
        # Configure grid
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Wizard state
        self.current_screen = 0
        self.screens = []
        self.scan_mode = "full"
        self.min_size_mb = 10
        self.selected_paths = []
        self.export_options = {}
        self.categories = {}
        self.analysis_results = []
        
        # Create screens
        self.create_screens()
        
        # Show first screen
        self.show_screen(0)
        
    def create_screens(self):
        """Create all wizard screens"""
        self.screens = [
            WelcomeScreen(self, self),
            DriveSelectionScreen(self, self),
            AnalysisOptionsScreen(self, self),
            AnalysisProgressScreen(self, self),
            ResultsDashboardScreen(self, self)
        ]
        
    def show_screen(self, index: int):
        """Show specific screen"""
        if 0 <= index < len(self.screens):
            # Hide all screens
            for screen in self.screens:
                screen.grid_remove()
                
            # Show selected screen
            self.current_screen = index
            self.screens[index].grid(row=0, column=0, sticky="nsew")
            self.screens[index].on_show()
            
    def next_screen(self):
        """Go to next screen"""
        if self.screens[self.current_screen].validate():
            if self.current_screen < len(self.screens) - 1:
                self.show_screen(self.current_screen + 1)
                
    def prev_screen(self):
        """Go to previous screen"""
        if self.current_screen > 0:
            self.show_screen(self.current_screen - 1)

def main():
    """Run the GUI application"""
    # Check for required modules
    try:
        import customtkinter
        import matplotlib
    except ImportError as e:
        print(f"Error: Missing required module - {e}")
        print("\nPlease install required modules:")
        print("pip install -r requirements.txt")
        sys.exit(1)
        
    # Create and run application
    app = DiskAnalyzerWizard()
    app.mainloop()

if __name__ == "__main__":
    main()