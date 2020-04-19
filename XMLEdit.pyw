#!/usr/bin/env python

from __future__ import print_function

try:  # python2 imports
    import Tkinter as tk
    from tkMessageBox import showerror
    from tkMessageBox import messagebox
    import ttk
    from tkFileDialog import askdirectory
    print('python2 detected')
except ImportError:  # try python3 imports
    import tkinter as tk
    from tkinter import ttk
    from tkinter.filedialog import askdirectory
    from tkinter.messagebox import showerror
    from tkinter import messagebox
    basestring = str
    print('python3 detected')
import re
import codecs
import os
from functools import partial
import bs4
import json
import time
import sys
import types
from  pagination import *


# Page label states
NOT_SELECTED = 0
SELECTED = 1

NORMAL_STATE = 0
ACTIVE_STATE = 1


__version__ = (0,2)
debug = False

# load global options dictionary
opt_fn = "reader_options.json"

# default options
opt = {
    'dir': None, # last seen directory
    'geometry': "350x550",
    'save_position': True, # save the geometry and position of the window and restore on next load
    'MS_format_output': True, # convert output to microsoft .NET style
    'formats': '.config .xml', # extensions of files to be listed; space delimited
    'entrybox_width': 25,  # width of the entry boxes
    'output_encoding': 'autodetect', # any valid encoding ('utf-8', 'utf-16le', etc) or autodetect.
    'backup_ext': '.bak', # extension of backed up files. Use something not in 'formats' to prevent backups from showing in the dropdown list.
    }

try:
    with open(opt_fn) as f:
        opt.update(json.load(f))
except Exception as e:
    print("default options used due to", e)

class FilePicker(tk.Frame):
    def __init__(self, master, command=None):
        tk.Frame.__init__(self, master)
        self.command = command

        hlm = tk.Frame(self)
        hlm.pack(fill=tk.X, expand=tk.TRUE)
        self.fold = AutoSelectEntry(hlm, command=self.browse)
        self.fold.pack(side=tk.LEFT, fill=tk.X, expand=tk.TRUE)
        btn = ttk.Button(hlm, text="...", width=3, command=self.browse)
        btn.pack(side=tk.LEFT)

        hlm = tk.Frame(self)
        hlm.pack(fill=tk.X, expand=tk.TRUE)
        self.file = tk.StringVar(self)
        self.file.set("Select a File")
        self.files = ttk.OptionMenu(hlm, self.file)
        self.files.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn = ttk.Button(hlm, text="Save", command=master.save)
        btn.pack(side=tk.LEFT)

    def update_options(self, options):
        self.files['menu'].delete(0, tk.END)
        for option in options:
            self.files['menu'].add_command(label=option, command=partial(self.run_command, option))
        self.file.set("Select a File")

    def run_command(self, fn):
        try:
            if self.command:
                self.command(os.path.join(self.fold.get(), fn))
            self.file.set(fn)
        except Exception as e:
            showerror("File Load Error", "%s is not a valid XML file.\n%s"%(fn, e))
            if debug: raise

    def browse(self, dir=None):
        if dir is None:
            dir = askdirectory(initialdir=opt.get('dir'))
        if dir: # check for user cancelled
            result = self.load_dir(dir)
            if hasattr(self.master, 'status'):
                self.master.status.set(result)

    def load_dir(self, dir):
        try:
            fns = os.listdir(dir)
        except Exception as e:
            print("could not load folder:", e)
            return "invalid folder"
        opt['dir'] = dir
        self.fold.set(dir)
        file_types = [x.strip() for x in opt['formats'].split()]
        dir = [fn for fn in fns if any(fn.endswith(x) for x in file_types)]
        self.update_options(dir)
        return "{} files found".format(len(dir))

    def load_path(self, path):
        dir, fn = os.path.split(path)
        self.load_dir(dir)
        self.run_command(fn)


class VerticalScrolledFrame:
	"""
	A vertically scrolled Frame that can be treated like any other Frame
	ie it needs a master and layout and it can be a master.
	keyword arguments are passed to the underlying Canvas (eg width, height)
	"""
	def __init__(self, master, **kwargs):
		self.outer = tk.Frame(master)

		self.vsb = tk.Scrollbar(self.outer, orient=tk.VERTICAL)
		self.vsb.pack(fill=tk.Y, side=tk.RIGHT)
		self.canvas = tk.Canvas(self.outer, highlightthickness=0, **kwargs)
		self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
		self.canvas['yscrollcommand'] = self.vsb.set
		self.canvas.bind("<Enter>", self._bind_mouse)
		self.canvas.bind("<Leave>", self._unbind_mouse)
		self.vsb['command'] = self.canvas.yview

		self.inner = tk.Frame(self.canvas)
		# pack the inner Frame into the Canvas with the topleft corner 4 pixels offset
		self.canvas.create_window(4, 4, window=self.inner, anchor='nw')
		self.inner.bind("<Configure>", self._on_frame_configure)

		self.outer_attr = set(dir(tk.Widget))
		self.frames = (self.inner, self.outer)

	def __getattr__(self, item):
		"""geometry attributes etc (eg pack, destroy, tkraise) are passed on to self.outer
		all other attributes (_w, children, etc) are passed to self.inner"""
		return getattr(self.frames[item in self.outer_attr], item)

	def _on_frame_configure(self, event=None):
		self.canvas.configure(scrollregion=self.canvas.bbox("all"))

	def _bind_mouse(self, event=None):
		"""mouse event bind does not work, so this hack allows the use of bind_all
		Linux uses Buttons, Windows/Mac uses MouseWheel"""
		for ev in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
			self.canvas.bind_all(ev, self._on_mousewheel)

	def _unbind_mouse(self, event=None):
		for ev in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
			self.canvas.unbind_all(ev)

	def _on_mousewheel(self, event):
		"""Linux uses event.num; Windows / Mac uses event.delta"""
		if event.num == 4 or event.delta == 120:
			self.canvas.yview_scroll(-1, "units" )
		elif event.num == 5 or event.delta == -120:
			self.canvas.yview_scroll(1, "units" )


class AutoSelectEntry(ttk.Entry):
    elements = []

    def __init__(self, master, command=None, **kwargs):
        """Entry widget that auto selects when focused
        command is a function to execute on value change"""
        ttk.Entry.__init__(self, master, **kwargs)
        self.command = command
        self.old_value = None
        self.elements.append(self)
        self.dirty = False

        self.bind('<FocusIn>', self.select_all)
        self.bind('<Return>', self.input_change)
        self.bind('<FocusOut>', self.input_change)

    def select_all(self, event=None):
        self.selection_range(0, tk.END)

    def input_change(self, event=None, value=None):
        if value is None:
            value = self.get()
        if self.command is not None:
            if value == self.old_value:
                return # check for a change; prevent command trigger when just tabbing through
            self.dirty = True
            self.old_value = value
            self.command(value)
        self.select_all()

    def set(self, text=None, run=False):
        if text is None:
            text = ""
        if len(text) > 500:
            text = "<too long to display>"
        self.delete(0, tk.END)
        self.insert(0, text)
        self.old_value = text
        if run:
            self.input_change(text)


class GUI(tk.Frame):
    def __init__(self, master):
        tk.Frame.__init__(self, master)

        self.fn = None
        self.bs = None
        self.total_len = 0
        self.page_size = 0
        self.page_number = 0
        self.page_naxt = 0
        self.attr_size = 0
        self.item=[]
        self.isLoaded = True
        self.comments = []
        master.title("Config File Editor")
        icon = tk.PhotoImage(data=icondata)
        master.tk.call('wm', 'iconphoto', master._w, icon)
        master.geometry(opt.get('geometry'))
        master.protocol('WM_DELETE_WINDOW', self._quit)
        master.bind("<Control - S>", self.save)
        master.bind("<Control - s>", self.save)
        page = tk.Frame(self)
        page.pack()
        
        self.top = FilePicker(self, command=self.load_file)
        self.top.pack(fill=tk.X)
        self.top.load_dir(opt.get('dir') or os.getcwd())

        self.data_frame = tk.Frame(self)
        self.display = VerticalScrolledFrame(self.data_frame)
        self.display.pack(fill=tk.BOTH, expand=True)
        self.data_frame.pack(fill=tk.BOTH, expand=True)

        self.status = tk.StringVar(self, "Version: "+".".join(map(str,__version__)))
        lbl = ttk.Label(self, textvariable=self.status)
        lbl.pack(fill=tk.X)
        

    def _quit(self):
        if opt.get('save_position'):
            opt['geometry'] = self.master.geometry()
        else:
            # strip the position information; keep only the size information
            opt['geometry'] = self.master.geometry().split('+')[0]
        self.master.destroy()

    def get_xml_items(self,start):
        children = list(filter(istag, start.children))
        for child in children:
            self.item.append(child)
            #yield child

    def load_file(self, fn):
        print('loading', fn)
        self.fn = os.path.normpath(fn)
        AutoSelectEntry.elements = []
        # "rb" mode is python 2 and 3 compatibe; BS handles the unicode conversion.
        with open(fn, 'rb') as f:
            self.bs = bs4.BeautifulSoup(f, 'xml')
        elements = []
        self.comments = []
        for e in self.bs.contents:
            if istag(e):
                elements.append(e)
            elif isinstance(e, basestring):
                self.comments.append(e)
            else:
                print("WARNING: unidentified elements found:", e)
        if len(elements) > 1:
            print("WARNING: %s root elements found; one expected")
        assert elements, "No XML data found"

        if self.display is not None:
            print('Destroying Display')
            self.display.destroy()
            del self.display
        
        self.Mstart = elements[0]
        self.display = VerticalScrolledFrame(self.data_frame)
        self.item = []
        self.get_xml_items(self.Mstart)

        if self.comments :
            hlm = ttk.LabelFrame(self.display, text="File Comments")
            for comm in self.comments:
                lbl = tk.Label(hlm, text=comm, anchor='w', wraplength=300, justify=tk.LEFT)
                lbl.pack(fill=tk.X)
            hlm.pack()
        else :
            hlm = ttk.LabelFrame(self.display, text="File Comments")
            hlm.pack()

        
        children = list(filter(istag, self.Mstart.children))
        self.total_len = len(children)
        
        self.display.pack(pady=10,expand=True, fill=tk.BOTH)
        core = self.make_first_frame(self.display, self.Mstart)
        core.pack()
        if self.isLoaded == True:
            self.page = Pagination(self.data_frame, 1, self.total_len+1, command=self.my_display, pagination_style=pagination_style2)
            self.page.pack()
            self.isLoaded = False
        
    
    def save(self, event=None):
        print("Saving data")

        # trigger current variable if needed
        current = self.focus_get()
        if hasattr(current, 'input_change'):
            current.input_change()

        try:
            self.save_core()
        except Exception as e:
            showerror("Save Error", "Could not save file.\n"+str(e))
            if debug: raise

    def save_core(self):
        if self.fn is None:
            print("cannot save - no file loaded")
            self.status.set("cannot save - no file loaded")
            return
        name, ext = os.path.splitext(self.fn)
        #bkup_name = name + time.strftime("_%Y-%m-%d_%H-%M-%S") + ext + opt['backup_ext']
        os.rename(self.fn, name)
        print(self.fn, "backed up to", name)

        # whatever weirdness Andrew uses encodes in utf-16 and with windows-style line endings ... so I will too.
        # but beautifulsoup insists on normal output, so have to change it first.
        encoding = opt['output_encoding']
        if encoding == 'autodetect':
            encoding = self.bs.original_encoding
            print(encoding, "encoding autodetected")
            if encoding.startswith('utf-16'): # remove the "le" (MS BOM)
                encoding = 'utf-16'

        data = self.bs.prettify()
        if opt.get("MS_format_output"):
            data = MSiffy(data)
        data = data.replace('\n', '\r\n')  # Windows ... (sigh)
        data = data.replace('utf-8', encoding, 1)  # BS insists on utf8 output from prettify

        with codecs.open(self.fn, 'w', encoding) as f:
            f.write(data)

        for element in AutoSelectEntry.elements:
            element.dirty = False
        self.status.set("File backed up and saved.")
    
    def making_item(self, frame, bs): 
        children = list(filter(istag, bs))
        idx = 0
        num_attributes = len(bs.attrs)
        num_text = 0 if bs.string is None else 1
        if debug:
            print("{}: {} attributes; {} text; {} grandchildren".format(bs.name, num_attributes, num_text, len(children)))

        for attr, value in bs.attrs.items():
            # attribute entry
            idx = self.make_entry(frame, idx, attr, value.strip(), partial(self.change_attr, bs, attr))
        if bs.string is not None:
            # text entry
            idx = self.make_entry(frame, idx, "", bs.text.strip(), partial(self.change_attr, bs, None))
        
        for child in children:
            num_children = len(child.findChildren()) + len(child.attrs)
            if num_children == 0 and child.string is not None:
                # special case of only 1 text - making entry
                idx = self.make_entry(frame, idx, child.name, child.string.strip(), partial(self.change_attr, child, None))
            elif num_children > 0:
                # child has one attribute or one grandchild; make new frame
                h = self.make_label_frame(frame, child)
                h.grid(row=idx, column=0, columnspan=2, sticky='ew', padx=10, pady=10)
                idx += 1
    
    def make(self, frame, bs):
        idx = 0
        for attr, value in bs.attrs.items():
            # attribute entry
            idx = self.make_entry(frame, idx, attr, value.strip(), partial(self.change_attr, bs, attr))
        if bs.string is not None:
            # text entry
            idx = self.make_entry(frame, idx, "", bs.text.strip(), partial(self.change_attr, bs, None))

    def my_display(self,button_click):
        self.display.destroy()
        bs = []
        self.display = VerticalScrolledFrame(self.data_frame)
        frame = ttk.LabelFrame(self.display, text=self.Mstart)

        if button_click is "First":
            if self.comments:
                hlm = ttk.LabelFrame(self.display, text="File Comments")
                for comm in self.comments:
                    lbl = tk.Label(hlm, text=comm, anchor='w', wraplength=300, justify=tk.LEFT)
                    lbl.pack(fill=tk.X)
                hlm.pack()
            core = self.make_first_frame(self.display, self.Mstart)
            core.pack()
            self.page_number = 0
            frame.pack()
            self.display.pack(pady=10,expand=True, fill=tk.BOTH)
            return
        elif button_click is "Prev":
            self.page_number -= 1
            if self.page_number <= 0:
                if self.comments:
                    hlm = ttk.LabelFrame(self.display, text="File Comments")
                    for comm in self.comments:
                        lbl = tk.Label(hlm, text=comm, anchor='w', wraplength=300, justify=tk.LEFT)
                        lbl.pack(fill=tk.X)
                    hlm.pack()
                core = self.make_first_frame(self.display, self.Mstart)
                core.pack()
                self.page_number = 0
                frame.pack()
                self.display.pack(pady=10,expand=True, fill=tk.BOTH)
                return
            else:
                bs = self.item[self.page_number-1]
        elif button_click is "Next":
            bs = self.item[self.page_number]
            self.page_number += 1
            self.page_naxt = True
        elif button_click is "Last":
            bs = self.item[self.total_len -1]
            self.page_number = self.total_len 
            
        self.core = self.make_label_frame(frame, bs)
        self.core.pack()
        frame.pack()
        self.display.pack(pady=10,expand=True, fill=tk.BOTH)

 

    @staticmethod
    def make_entry(master, row, name, value, command):
        lbl = tk.Label(master, text=name, anchor='e')
        lbl.grid(row=row, column=0, sticky='ew')
        ent = AutoSelectEntry(master, width=opt['entrybox_width'], command=command)
        ent.set(value)
        ent.grid(row=row, column=1, sticky='e')
        return row + 1

    def make_label_frame(self, master, bs):
        frame = ttk.LabelFrame(master, text=bs.name)
        hlm = tk.Frame(frame)
        hlm.columnconfigure(0, weight=1)
        self.making_item(hlm, bs)
        hlm.pack(side=tk.RIGHT)
        return frame

    def make_first_frame(self, master, bs):
        frame = ttk.LabelFrame(master, text=bs.name)
        hlm = tk.Frame(frame)
        hlm.columnconfigure(0, weight=1)
        self.make(hlm, bs)
        hlm.pack(side=tk.RIGHT)
        return frame

    def dirty_status(self):
        changes = "{} unsaved changes".format(sum(x.dirty for x in AutoSelectEntry.elements))
        print(changes)
        self.status.set(changes)

    def change_attr(self, bs, attr, new_text):
        if attr is None:
            bs.string = new_text
        else:
            bs[attr] = new_text
        self.dirty_status()


def istag(test):
    return isinstance(test, bs4.Tag)


def MSiffy(data):
    """convert the beautifulsoup prettify output to a microsoft .NET style
    Basically this means moving the contents of tags into the same line as the tag"""
    hlm = []
    state = False
    leading_spaces = re.compile(r"^\s*")
    for line in data.splitlines():
        if "<" in line:
            if state:
                line = line.strip()
            else:
                spaces = leading_spaces.search(line).group(0)
                line = spaces + line
            hlm.append(line)
            state = False
        else:
            hlm.append("\n" + line.strip() + "\n")
            state = True
    nd = "\n".join(hlm)
    return nd.replace("\n\n", "")


def main():
    root = tk.Tk()
    window = GUI(root)
    window.pack(fill=tk.BOTH, expand=True)

    if len(sys.argv) > 1:
        window.top.load_path(" ".join(sys.argv[1:]))
    root.mainloop()
    with open(opt_fn, 'w') as f:
        json.dump(opt, f, indent=2)


# icon as a base64 encoded gif.
icondata = """
R0lGODlhgACAAOf/AAABAAYDCQAFCAMKDQkMCA4LEAMOFQsMFQsQExARGQoTGQ4SHRAXHRIWIg4Y
IhYYFhUYGhYaJRoeKRYgKh4fIh4gHRggMBwjLhsjMyIjISElJyElLCclKR8nNyYnJSMqOiQsNyEt
QiktMiwtKycuPyYyRzAyLyk0SS41PDM2OC44Qyw4TTE4Sjc5Nio7VTA7US4+WTY/SjQ/VT0/PD4/
QkBCPzNDXkFCSjZGYUVHREBHWDVKajtKZj9KYUhKR0dLTUdLUz5OaTpPb0RPZlBOUE5QTT5Tc0tS
WUJWd05WYlRWU0hXcVRXWUVZek5YakBagERehFtcWkpef1VecFBffFxfYkhiiEZijlhgbVlhaGBi
X1hje0xmjEhnk09lk2dlaVBpkFZoiWZnZWNoamJqcWNqeE5tml9rfVNtlFhtnF9tiWttampucVdw
l3BtcVNynm5wbWhxf1Z0oV5zoll0qHJ0cV12nnZzd1p4pnZ3dGh5k117qHl6d2Z7ql99q2F8sHx6
fm18mnR8i3t8eWh9rGKArWR/s3l+gX1+fF6CtYF+gmSCsIN+fX6AfWaDsWGEt3+BfnSDoWmEuYGD
gIeCgWOHum+FrIWDh32FjICFh2aJvW2IvX6Hl4aIhWmMwHGLwImLiGuPw4aNlY2NkG6RxnSSwXaR
x46QjYKRsHuUvXOWym6X0XaV0ZOVkpaUmYmWrHGa1HiY1HeZzpaYlXSd13ub14+ap3qgzneg2n+e
2pudmp+doXqj3YKh3pyhpJ+hnn6m4Yal4pulsIKq5YSp66amqqWnpICv8Imt8KqsqYiw64ux36+t
saivtIWz9I2x9LCyr4y37I628Ym3+JG1+JO3+q62vrG2uI+5/7e1uZW5/LW3tJC9/5i+7ZbB9ry9
urm+wb+9wcDCv8fCwaHN+MvGxMbIxMnIzMnLyNDSz87S1dvX2Nja197g3ePg5d3i5enj4uPl4ujp
5uvp7ezu6/Dy7/Ty9vH2+fX28/759/n79/b8/v77//z++/7//P///yH5BAEKAP8ALAAAAACAAIAA
AAj+AP8JHEiwoMGDCBMqXMiwocOHECNKnEixosWLGC9isGAho8ePICV+CNEBA4aQKFOq/OfCRYgV
NkKsnElzYggbT3Ag8SRHZs2fQBGG+GDFzJtctMAEXfqRI0McDWC82USs1iobTLNW7FByo0IrISZY
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
277928Ad3MI93MRd3AEBADs=
"""

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        showerror("Fatal error!", "Config Editor crashed.\n\n"+str(e))
        raise
