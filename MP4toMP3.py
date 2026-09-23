#IN THE READ ME I NEED TO INCLUDE pip install moviepy

#add show file size

#The MP4toMP3 prototype converter

import os
import threading # this was needed to prevent the window from freezing during conversion
import tkinter as tk # basically jswing. for UI
from tkinter import filedialog, messagebox

from moviepy import VideoFileClip #needed to open mp4s and access the audio


def select_mp4(): # function to select the mp4 file
    path = filedialog.askopenfilename(
        title="Select an MP4 file",
        filetypes=[("MP4 files", "*.mp4")], #only show mp4 files
    )
    if path: # if user selects an mp4file
        file_label.config(text=os.path.basename(path), fg="black") # cosmetic, makes it show the file name instead of the full path
        convert_btn.config(state="normal")
        # stores the file path to convert
        root.selected_file = path

# runs when pressing the convert button
def convert():
    # ask where to save the MP3
    save_path = filedialog.asksaveasfilename(
        title="Save MP3 as...",
        defaultextension=".mp3", # makes the file type mp3
        filetypes=[("MP3 files", "*.mp3")], #show mp3
        initialfile=os.path.splitext(os.path.basename(root.selected_file))[0] + ".mp3", # keeps the same name as the original mp4 file, but now, surprisingly, it is an mp3 file
    )
    if not save_path:
        return  # cancelled

    # disable the button while converting
    convert_btn.config(state="disabled", text="Converting...")
    root.update_idletasks()

    # convert in a background so the window doesn't freeze
    threading.Thread(target=do_convert, args=(root.selected_file, save_path), daemon=True).start()


# the actual mp4 to mp3 conversion
def do_convert(input_file, output_file):
    try:
        clip = VideoFileClip(input_file) # open mp4

        #takes the audio of the mp4 and rips it as an mp3
        # logger=None is needed to prevent moviepy from printing to the terminal
        clip.audio.write_audiofile(output_file, logger=None)
        clip.close() #closes the mp4 when done

        # update UI back on the main thread
        root.after(0, lambda: finish_conversion(output_file))
    except Exception as e:
        root.after(0, lambda: fail_conversion(e))


def finish_conversion(output_file): #turns the converter button back on
    convert_btn.config(state="normal", text="Convert")
    messagebox.showinfo("Done", f"Saved to:\n{output_file}") # shows where the mp3 was saved


def fail_conversion(error): #turns the button back on but sad this time. Failure
    convert_btn.config(state="normal", text="Convert")
    messagebox.showerror("Error", f"Conversion failed:\n{error}") # error message


####################### UI

#this is not final. This is just meant to be a basic no feature UI. I don't think we will actually use only tkinter. If something looks wrong ingore it. All that matters is it works.

root = tk.Tk() # main window
root.title("MP4 to MP3 Converter")
root.geometry("420x230")
root.resizable(False, False)

tk.Label(root, text="MP4 → MP3 Converter", font=("Arial", 14, "bold")).pack(pady=10)

select_box = tk.Button( #mp4 select button
    root,
    text="Select an MP4 file",
    width=40,
    height=4,
    relief="ridge",
    bg="#ffffff",
    command=select_mp4,
)
select_box.pack(pady=10)

file_label = tk.Label(root, text="No file selected", fg="gray", wraplength=380) # wrap
file_label.pack(pady=5) #name file in window

convert_btn = tk.Button(root, text="Convert", width=20, state="disabled", command=convert) #convert button
convert_btn.pack(pady=10)

root.mainloop() #tkinter event loop. Makes the buttons work and window stay open. Think jswing