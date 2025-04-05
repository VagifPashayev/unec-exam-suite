import os
import json
from tkinter import *
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
from pdf2image import convert_from_path

# Path to Poppler binaries — required on Windows.
# Download from: https://github.com/oschwartz10612/poppler-windows/releases
# Set the POPPLER_PATH environment variable or update the fallback below.
POPPLER_PATH = os.environ.get("POPPLER_PATH", r"C:\Program Files\poppler\Library\bin")

start_x = start_y = 0
rect_id = None
rect = None
current_image = None
imgtk = None
page_images = []
page_index = 0
question_index = 1
step_index = 0
step_labels = ['question', 'a', 'b', 'c', 'd', 'e']
crop_data = {}
save_dir = "quiz_data"
metadata_path = os.path.join(save_dir, "metadata.json")

os.makedirs(save_dir, exist_ok=True)


def load_existing_metadata():
    global crop_data, question_index, step_index
    if os.path.exists(metadata_path):
        with open(metadata_path, "r", encoding="utf-8") as f:
            crop_data = json.load(f)
        if crop_data:
            last_q = sorted(crop_data.keys(), key=lambda x: int(x[1:]))[-1]
            question_index = int(last_q[1:]) + 1
            step_index = 0


load_existing_metadata()


def load_pdf():
    global page_images, page_index
    filepath = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
    if filepath:
        page_images = convert_from_path(filepath, dpi=200, poppler_path=POPPLER_PATH)
        page_index = 0
        show_page()


def show_page():
    global current_image, imgtk
    img = page_images[page_index]
    current_image = img
    imgtk = ImageTk.PhotoImage(img)
    canvas.delete("all")
    canvas.create_image(0, 0, anchor=NW, image=imgtk)
    update_label()
    status_label.config(text=f"Page {page_index + 1}/{len(page_images)} — Question {question_index}")


def update_label():
    if step_index < len(step_labels):
        label.config(text=f"[Question {question_index}] — select the {step_labels[step_index].upper()} region")
    else:
        label.config(text=f"[Question {question_index}] — enter the correct answer (a/b/c/d/e)")


def on_mouse_down(event):
    global start_x, start_y, rect_id
    start_x, start_y = canvas.canvasx(event.x), canvas.canvasy(event.y)
    rect_id = canvas.create_rectangle(start_x, start_y, start_x, start_y, outline="red", width=2)


def on_mouse_drag(event):
    x, y = canvas.canvasx(event.x), canvas.canvasy(event.y)
    canvas.coords(rect_id, start_x, start_y, x, y)


def on_mouse_up(event):
    global rect
    end_x, end_y = canvas.canvasx(event.x), canvas.canvasy(event.y)
    rect = (min(start_x, end_x), min(start_y, end_y), max(start_x, end_x), max(start_y, end_y))
    confirm_crop()


def on_escape(event):
    global rect_id
    if rect_id:
        canvas.delete(rect_id)
        rect_id = None


def confirm_crop():
    result = messagebox.askyesno("Confirm", "Save this region?")
    if result:
        save_crop()
    else:
        canvas.delete(rect_id)


def save_crop():
    global step_index, question_index, crop_data
    if rect and current_image:
        crop = current_image.crop(rect)
        label_name = step_labels[step_index]
        filename = f"q{question_index}_{label_name}.png"
        filepath = os.path.join(save_dir, filename)
        crop.save(filepath)

        qkey = f"q{question_index}"
        if qkey not in crop_data:
            crop_data[qkey] = {"question": "", "options": {}, "correct": "", "extra": []}

        if label_name == 'question':
            crop_data[qkey]["question"] = filename
        else:
            crop_data[qkey]["options"][label_name] = filename

        step_index += 1

        if step_index == len(step_labels):
            ask_correct_answer()

        update_label()
        save_metadata()


def ask_correct_answer():
    popup = Toplevel(root)
    popup.title("Correct answer")
    popup.geometry("300x150")
    popup.transient(root)
    popup.grab_set()

    Label(popup, text="Which option is correct? (a/b/c/d/e)").pack(pady=10)
    entry = Entry(popup)
    entry.pack(pady=5)
    entry.focus_set()

    def on_submit():
        val = entry.get().strip().lower()
        if val in ['a', 'b', 'c', 'd', 'e']:
            crop_data[f"q{question_index}"]["correct"] = val
            popup.destroy()
            ask_if_more_parts()
        else:
            messagebox.showwarning("Invalid input", "Please enter a valid option (a/b/c/d/e).")

    Button(popup, text="Confirm", command=on_submit).pack(pady=10)
    popup.protocol("WM_DELETE_WINDOW", popup.destroy)


def ask_if_more_parts():
    global step_index, question_index
    result = messagebox.askyesno(
        "Multi-page question",
        "Does this question continue on another page?",
        default="no",
    )
    if result:
        messagebox.showinfo("Continue", "Select the remaining region on the next page.")
        step_index = 0
    else:
        step_index = 0
        question_index += 1
    save_metadata()
    update_label()


def save_metadata():
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(crop_data, f, indent=4)


def next_page():
    global page_index
    if page_index < len(page_images) - 1:
        page_index += 1
        show_page()


def prev_page():
    global page_index
    if page_index > 0:
        page_index -= 1
        show_page()


def delete_current_question():
    global question_index, step_index
    qkey = f"q{question_index}"
    if qkey in crop_data:
        for img in [crop_data[qkey].get("question", "")] + list(crop_data[qkey].get("options", {}).values()):
            try:
                os.remove(os.path.join(save_dir, img))
            except OSError:
                pass
        del crop_data[qkey]
        question_index = max(1, question_index - 1)
        step_index = 0
        save_metadata()
        update_label()
        messagebox.showinfo("Deleted", f"{qkey} removed.")


def scale_canvas(factor):
    global imgtk, current_image
    w, h = current_image.size
    new_size = (int(w * factor), int(h * factor))
    resized = current_image.resize(new_size)
    imgtk = ImageTk.PhotoImage(resized)
    canvas.delete("all")
    canvas.create_image(0, 0, anchor=NW, image=imgtk)
    canvas.config(scrollregion=(0, 0, *new_size))


# --- GUI setup ---

root = Tk()
root.title("Quiz Creator")
root.state("zoomed")

frame = Frame(root)
frame.pack()

Button(frame, text="Load PDF", command=load_pdf).pack(side=LEFT)
Button(frame, text="<< Prev page", command=prev_page).pack(side=LEFT)
Button(frame, text="Next page >>", command=next_page).pack(side=LEFT)
Button(frame, text="Delete question", command=delete_current_question).pack(side=LEFT)

label = Label(root, text="Load a PDF to begin", font=("Arial", 14))
label.pack()

status_label = Label(root, text="", font=("Arial", 12))
status_label.pack()

scroll_y = Scrollbar(root, orient=VERTICAL)
scroll_y.pack(side=RIGHT, fill=Y)

scroll_x = Scrollbar(root, orient=HORIZONTAL)
scroll_x.pack(side=BOTTOM, fill=X)

canvas = Canvas(
    root, width=1600, height=1200, bg="gray",
    yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set,
    scrollregion=(0, 0, 3000, 3000),
)
canvas.pack(fill=BOTH, expand=YES)
canvas.bind("<ButtonPress-1>", on_mouse_down)
canvas.bind("<B1-Motion>", on_mouse_drag)
canvas.bind("<ButtonRelease-1>", on_mouse_up)
canvas.bind("<Escape>", on_escape)
canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

scroll_y.config(command=canvas.yview)
scroll_x.config(command=canvas.xview)

root.bind("<Control-plus>", lambda e: scale_canvas(1.1))
root.bind("<Control-minus>", lambda e: scale_canvas(0.9))

root.mainloop()
