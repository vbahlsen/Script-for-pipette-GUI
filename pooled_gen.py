import csv
import datetime
import os
import matplotlib.pyplot as plt
import numpy as np
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import screeninfo

class CustomDropdown:
    def __init__(self, master, values, **kwargs):
        self.master = master
        self.values = values
        self.selected_value = tk.IntVar(value=values[0])  # Sett initialverdi

        # Tilpass utseendet her
        self.button_width = kwargs.get("width", 5)
        self.button_height = kwargs.get("height", 1)
        self.listbox_width = kwargs.get("listbox_width", self.button_width)
        self.listbox_height = kwargs.get("listbox_height", 5)
        self.font = kwargs.get("font", ("Helvetica", 28))

        # Simuler Combobox-knappen
        self.button = tk.Button(master, textvariable=self.selected_value, command=self.show_dropdown,
                                width=self.button_width, height=self.button_height, font=self.font)
        # self.button.pack() # Pakk knappen i generate_list_gui i stedet

        self.dropdown_window = None
        self.listbox = None

    def show_dropdown(self):
        if self.dropdown_window:
            self.dropdown_window.destroy()
            self.dropdown_window = None
            return

        # Lag et Toplevel-vindu for nedtrekksmenyen
        self.dropdown_window = tk.Toplevel(self.master)
        self.dropdown_window.overrideredirect(True)  # Fjern tittellinje og ramme

        # Sett Toplevel-vinduet til å være i forgrunnen
        self.dropdown_window.attributes("-topmost", True)

        # Posisjoner vinduet under knappen
        x = self.button.winfo_rootx()
        y = self.button.winfo_rooty() + self.button.winfo_height()
        self.dropdown_window.geometry(f"+{x}+{y}")

        # Lag en Listbox for valgene
        self.listbox = tk.Listbox(self.dropdown_window, width=self.listbox_width, height=self.listbox_height, font=self.font)
        for value in self.values:
            self.listbox.insert(tk.END, value)
        self.listbox.pack()

        # Velg et element
        self.listbox.bind("<<ListboxSelect>>", self.select_item)

        # Skjul vinduet når brukeren klikker utenfor
        self.dropdown_window.bind("<FocusOut>", self.hide_dropdown)

    def select_item(self, event):
        try:
            index = self.listbox.curselection()[0]
            selected = self.listbox.get(index)
            self.selected_value.set(selected)
            self.hide_dropdown()
        except IndexError:
            pass

    def hide_dropdown(self, event=None):
        if self.dropdown_window:
            self.dropdown_window.destroy()
            self.dropdown_window = None


def create_visualisation(all_cases, filename):
    """
    Generer en .jpg-fil av visualiseringen av prøvene i racks.
    """
    num_cases = max(all_cases)
    num_grids = (num_cases - 1) // 12 + 1
    grid_samples = np.zeros((num_grids, 6, 12), dtype=int)

    case_index = 0
    for case_number in range(1, num_cases + 1):
        samples = all_cases.count(case_number)
        grid_num = case_index // 12
        column = case_index % 12
        for row in range(samples):
            grid_samples[grid_num, row, column] = 1
        case_index += 1

    # Visualisering i Matplotlib
    fig, axes = plt.subplots(num_grids, 1, figsize=(15, num_grids * 6))
    if num_grids == 1:
        axes = [axes]

    for i, ax in enumerate(axes):
        ax.imshow(grid_samples[i], cmap='Oranges', interpolation='none', extent=[0, 12, 0, 6])
        for x in range(12):
            for y in range(6):
                if grid_samples[i, y, x] == 1:
                    ax.plot(x + 0.5, 5.5 - y, 'ro', markersize=30, markerfacecolor='red', markeredgewidth=2)
        ax.set_xticks(np.arange(0.5, 12.5, 1))
        ax.set_yticks(np.arange(0.5, 6.5, 1))
        ax.set_xticklabels(np.arange(1 + i * 12, 13 + i * 12))
        ax.set_yticklabels(np.arange(6, 0, -1))
        ax.set_title(f'Rack {i + 1}')
        ax.invert_yaxis()

    plt.tight_layout()
    plt.savefig(filename)  # Lagre figuren som .jpg
    plt.close() #Lukk figuren

def generate_list_gui():
    """
    GUI-basert versjon av generate_list.
    Bruker 5 dropdownmenyer for input og to knapper for kontroll.
    """
    root = tk.Tk()
    root.title("Prøve Generator")

    # Finn sekundærskjermen
    secondary_monitor = None
    for m in screeninfo.get_monitors():
        if not m.is_primary:
            secondary_monitor = m
            break

    if secondary_monitor is None:
        messagebox.showerror("Feil", "Fant ikke sekundærskjerm.")
        return

    # Tving GUI til sekundærskjermen og til å være i forgrunnen
    root.attributes("-topmost", True)
    root.geometry(f"+{secondary_monitor.x}+{secondary_monitor.y}")  # Plasser vinduet på sekundærskjermen

    screen_width = secondary_monitor.width
    screen_height = secondary_monitor.height
    root.geometry(f"{screen_width}x{int(screen_height * 0.6)}")  # Skalerer GUI til 60% av skjermen

    case_list = []
    total_samples = 0
    current_case_number = 1

    # Dropdownmenyer for antall saker med 1-5 prøver
    dropdown_values = list(range(0, 21))  # Velg antall saker fra 0 til 20
    dropdowns = []

    # Stor tittel
    title_label = tk.Label(root, text="Velg antall saker med prøver", font=("Helvetica", 18, "bold"))
    title_label.pack(pady=20)

    # Ramme med dropdownmenyer
    dropdown_frame = tk.Frame(root)
    dropdown_frame.pack(pady=10)
    for i in range(1, 6):
        row = tk.Frame(dropdown_frame)
        row.pack(pady=10)
        label = tk.Label(row, text=f"Antall saker med {i} prøver:", font=("Helvetica", 14))
        label.pack(side="left", padx=10)

        # Bruk CustomDropdown i stedet for ttk.Combobox
        dropdown = CustomDropdown(row, dropdown_values, width=5, height=1, listbox_width=5, listbox_height=21, font=("Helvetica", 28))
        dropdown.button.pack(side="left")
        dropdowns.append(dropdown)

    # Funksjon for å legge til en serie med prøver
    def add_series():
        nonlocal total_samples, current_case_number
        local_total = 0
        for idx, dropdown in enumerate(dropdowns):
            num_cases = dropdown.selected_value.get() # Hent verdien fra CustomDropdown
            local_total += num_cases * (idx + 2)
            for _ in range(num_cases):
                case_list.extend([current_case_number] * (idx + 2))
                current_case_number += 1
        total_samples += local_total

        if total_samples > 96:
            messagebox.showerror("Feil", "Totalt antall rader overstiger 96. Prøv igjen.")
            total_samples -= local_total
            case_list.clear()
            current_case_number = 1
        else:
            messagebox.showinfo("Suksess", f"Totalt antall rader hittil: {total_samples}")
            # Nullstill dropdownene
            for dropdown in dropdowns:
                dropdown.selected_value.set(0)

    # Knapp for å legge til ny serie
    add_button = tk.Button(root, text="Legg til ny serie", command=add_series, font=("Helvetica", 14), width=20, height=2)
    add_button.pack(pady=10)

    # Knapp for å generere liste og avslutte
    def finish():
        nonlocal total_samples, case_list, current_case_number
        local_total = 0
        for idx, dropdown in enumerate(dropdowns):
            num_cases = dropdown.selected_value.get() # Hent verdien fra CustomDropdown
            local_total += num_cases * (idx + 2)
            for _ in range(num_cases):
                case_list.extend([current_case_number] * (idx + 2))
                current_case_number += 1
        total_samples += local_total

        if total_samples > 96:
            messagebox.showerror("Feil", "Totalt antall rader overstiger 96. Prøv igjen.")
            total_samples -= local_total
            case_list.clear()
            current_case_number = 1
        elif total_samples == 0:
            messagebox.showerror("Feil", "Ingen saker lagt til. Legg til minst én serie.")
        else:
            root.destroy()

    finish_button = tk.Button(root, text="Generer liste", command=finish, font=("Helvetica", 14), bg="green", fg="white", width=25, height=2)
    finish_button.pack(pady=20)

    root.mainloop()
    return case_list

def main():
    DIRECTORY = r"C:\\Tecan\\Filer\\PJS_eksport"
    VISUALIZATION_FILE = r"C:\\Tecan\\Filer\\VisualiseringStorfe.jpg"
    #DIRECTORY = r"C:\\Users\\vi2121\\Desktop\\test"
    #VISUALIZATION_FILE = r"C:\\Users\\vi2121\\Desktop\\test\\VisualiseringStorfe.jpg"
    print("GUI åpnes for å legge til prøveserier...")

    all_cases = generate_list_gui()
    timestamp = datetime.datetime.now().strftime("%y%m%d %H%M")
    filename = os.path.join(DIRECTORY, f"Storfe {timestamp}.csv")

    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        for sample in all_cases:
            writer.writerow([sample])

    print(f"Liste lagret som {filename}")
    create_visualisation(all_cases, VISUALIZATION_FILE)
    print(f"Visualisering lagret som {VISUALIZATION_FILE}")

if __name__ == "__main__":
    main()