import io
import json
import os
import shutil
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext
import cairosvg
import chess
import chess.svg
import cv2
import google.generativeai as genai
import google.ai.generativelanguage as glm 
from PIL import Image, ImageTk
from openai import OpenAI
from stockfish import Stockfish
from ultralytics import YOLO
from dotenv import load_dotenv
from recognize_position import extract_FEN, orient_chessboard

GPT_MODEL = "gpt-4o"
GEMINI_MODEL = "gemini-2.5-flash-preview-04-17"
PIECES = {
    "P": "il pedone bianco",
    "N": "il cavallo bianco",
    "B": "l'alfiere bianco",
    "R": "la torre bianca",
    "Q": "la donna bianca",
    "K": "il re bianco",
    "p": "il pedone nero",
    "n": "il cavallo nero",
    "b": "l'alfiere nero",
    "r": "la torre nera",
    "q": "la donna nera",
    "k": "il re nero",
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "evaluate_move",
            "description": "Valuta una mossa in notazione UCI usando Stockfish nella posizione corrente",
            "parameters": {
                "type": "object",
                "properties": {
                    "move_uci": {
                        "type": "string",
                        "description": "Mossa UCI da valutare (es: 'e2e4', 'g1f3')"
                    }
                },
                "required": ["move_uci"]
            }
        }
    }
]

class ChessAssistantApp:
    def __init__(self, root, OPENAI_API_KEY, GEMINI_API_KEY):
        self.root = root
        self.root.title("Chess Assistant AI")
        self.root.attributes('-fullscreen', True)
        self.OPENAI_API_KEY = OPENAI_API_KEY
        self.GEMINI_API_KEY = GEMINI_API_KEY
        self.chessboard = chess.Board()
        self.old_fen = self.chessboard.board_fen()
        self.turn = "w"
        self.show_bounding_boxes = True
        self.automatic_detection = True
        self.first_automatic_detection = True
        self.create_layout()
        self.cap = cv2.VideoCapture(2)
        self.running = True
        self.castling = "KQkq"
        self.castle_blacklist = set()
        self.photo_number = 1
        self.stockfish = self.initialize_stockfish()
        self.orient_board()
        self.update_webcam()
        self.recognize_move_loop()

    def create_layout(self):
        # === FRAME SUPERIORE ===
        upper_frame = tk.Frame(self.root)
        upper_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        # Toolbar in alto
        toolbar = tk.Frame(upper_frame, height=40, bg="#3c3c3c")
        toolbar.pack(side=tk.TOP, fill=tk.X)
        # Pulsante "Orienta correttamente"
        orient_button = tk.Button(toolbar, text="Orienta correttamente", command=lambda: self.confirm("Riorientamento scacchiera", "Sei sicuro di voler riorientare la scacchiera?", "orienta"), font=("Helvetica", 12))
        orient_button.pack(side=tk.LEFT, padx=(5, 10), pady=5)
        # Checkbox per aggiungere o rimuovere le bounding boxes
        self.bounding_boxes_state = tk.BooleanVar()  # Variabile che memorizza lo stato della checkbox
        self.bounding_boxes_state.set(True)
        checkbox = tk.Checkbutton(toolbar, text="Bounding Boxes", variable=self.bounding_boxes_state, command=self.toggle_bounding_boxes, font=("Helvetica", 12), pady=6)
        checkbox.pack(side=tk.LEFT, padx=(0, 10), pady=5)
        # Checkbox per detection automatica
        self.detection_state = tk.BooleanVar()  # Variabile che memorizza lo stato della checkbox
        self.detection_state.set(True)
        checkbox = tk.Checkbutton(toolbar, text="Detection Automatica", variable=self.detection_state, command=self.toggle_detection, font=("Helvetica", 12), pady=6)
        checkbox.pack(side=tk.LEFT, padx=(0, 10), pady=5)
        # Pulsante "Esci" con icona
        power_icon = Image.open(os.path.join("icons","power.png"))
        power_icon = power_icon.resize((45, 32), Image.LANCZOS)
        self.power_img = ImageTk.PhotoImage(power_icon)
        quit_button = tk.Button(toolbar, image=self.power_img, command=lambda: self.confirm("Conferma uscita", "Sei sicuro di voler terminare l'applicazione?", "esci"), fg="#3c3c3c", borderwidth=0, highlightthickness=0, relief=tk.FLAT)
        quit_button.pack(side=tk.RIGHT, padx=(0, 10), pady=5)
        # Label "Tocca al..."
        self.turn_label = tk.Label(toolbar, text="", font=("Helvetica", 12, "bold"), fg="white", bg="#3c3c3c")
        self.turn_label.pack(side=tk.RIGHT, padx=10)
        # Pulsante per cambiare il colore del turno
        icon_image = Image.open(os.path.join("icons","change_turn.png"))
        icon_image = icon_image.resize((30, 30), Image.Resampling.LANCZOS)
        self.turn_icon = ImageTk.PhotoImage(icon_image)
        self.turn_button = tk.Button(toolbar, text="",image=self.turn_icon, command=self.switch_turn, compound=tk.LEFT, fg="#3c3c3c", relief=tk.FLAT, bd=0)
        self.turn_button.bind("<Enter>", lambda event: self.show_tooltip(event, "Cambia turno"))
        self.turn_button.bind("<Leave>", self.hide_tooltip)
        self.turn_button.pack(side=tk.RIGHT)
        self.update_turn_label()
        content_frame = tk.Frame(upper_frame)
        content_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        # Pulsante "Forza detection" con icona
        instant_detection = Image.open(os.path.join("icons","lente_ingrandimento.png"))
        instant_detection = instant_detection.resize((40, 32), Image.LANCZOS)
        self.detection_img = ImageTk.PhotoImage(instant_detection)
        self.instant_detection_button = tk.Button(toolbar, image=self.detection_img, command=self.make_detection, fg="#3c3c3c", borderwidth=0, highlightthickness=0, relief=tk.FLAT)
        self.instant_detection_button.pack(side=tk.RIGHT, padx=(0, 10), pady=5)
        self.instant_detection_button.bind("<Enter>", lambda event: self.show_tooltip(event, "Detection istantanea"))
        self.instant_detection_button.bind("<Leave>", self.hide_tooltip)
        self.instant_detection_button.config(state=tk.DISABLED)
        # Pulsante per ottenere mosse stockfish
        stockfish_icon = Image.open(os.path.join("icons", "stockfish.png"))
        stockfish_icon = stockfish_icon.resize((32, 32), Image.LANCZOS)
        self.stockfish_img = ImageTk.PhotoImage(stockfish_icon)
        self.stockfish_button = tk.Button(toolbar, image=self.stockfish_img, command=self.stockfish_suggestions, fg="#3c3c3c", borderwidth=0, highlightthickness=0, relief=tk.FLAT)
        self.stockfish_button.pack(side=tk.RIGHT, padx=(0, 10), pady=5)
        self.stockfish_button.bind("<Enter>", lambda event: self.show_tooltip(event, "Suggerisci le 5 mosse migliori Stockfish"))
        self.stockfish_button.bind("<Leave>", self.hide_tooltip)
        # Webcam view (Sinistra)
        self.video_label = tk.Label(content_frame)
        self.video_label.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        # Legenda al centro
        legend_frame = tk.Frame(content_frame, width=200)
        legend_frame.pack(side=tk.LEFT, padx=10, pady=10, fill=tk.Y)
        legend_label = tk.Label(legend_frame, text="Legenda", font=("Helvetica", 14, "bold"))
        legend_label.pack(pady=(0, 10))
        labels = [
            "0 = Pedone bianco",
            "1 = Torre bianca",
            "2 = Cavallo bianco",
            "3 = Alfiere bianco",
            "4 = Regina bianca",
            "5 = Re bianco",
            "6 = Pedone nero",
            "7 = Torre nera",
            "8 = Cavallo nero",
            "9 = Alfiere nero",
            "10 = Regina nera",
            "11 = Re nero"
        ]
        for label in labels:
            tk.Label(legend_frame, text=label, anchor="w", font=("Helvetica", 13)).pack(anchor="w")
        # Scacchiera (destra)
        self.chess_canvas = tk.Label(content_frame)
        self.chess_canvas.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH)
        # Label sopra la chat
        instruction_frame = tk.Frame(self.root, bg="#3c3c3c")
        instruction_frame.pack(side=tk.TOP, fill=tk.X, pady=(5, 0))  #Padding verticale aumentato
        instruction_label = tk.Label(instruction_frame, text="Fai domande all'Assistente AI sulla posizione:", font=("Helvetica", 13, "bold"), bg="#3c3c3c", fg="white", pady=8)
        instruction_label.pack()
        self.update_board()
        # === FRAME INFERIORE: CHAT ===
        lower_frame = tk.Frame(self.root, height=300, bg="#3c3c3c")
        lower_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.chat_area = scrolledtext.ScrolledText(lower_frame, wrap=tk.WORD, state='disabled', height=15)
        self.chat_area.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.chat_area.tag_config("sender_label", foreground="red", font=("Helvetica", 10, "bold"))
        self.chat_area.tag_config("user_label", foreground="blue", font=("Helvetica", 10, "bold"))
        self.chat_area.tag_config("user_message", foreground="purple")
        self.chat_area.tag_config("assistant", foreground="purple")
        self.user_input = tk.Entry(lower_frame)
        self.user_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)
        self.user_input.bind('<Return>', self.handle_user_input)
        send_button = tk.Button(lower_frame, text="Invia", command=self.handle_user_input)
        send_button.pack(side=tk.RIGHT, padx=5, pady=5)

    def show_tooltip(self, event, text):
        self.tooltip = tk.Label(self.root, text=text, background="#f0f0f0", relief="solid", borderwidth=1)
        self.tooltip.place(x=event.x_root + 10, y=event.y_root + 10)  # Posiziona il tooltip vicino al mouse

    def hide_tooltip(self, event):
        if hasattr(self, 'tooltip'):
            self.tooltip.destroy()
            
    def create_confirm_window(self, title_window, text):
        confirm_window = tk.Toplevel(self.root)
        confirm_window.withdraw()  # Nasconde la finestra per evitare lo sfarfallio
        confirm_window.title(title_window)
        win_width = 400
        win_height = 120
        confirm_window.geometry(f"{win_width}x{win_height}")
        confirm_window.resizable(False, False)
        confirm_window.grab_set()  # Blocca focus sulla finestra
        self.root.update_idletasks()
        confirm_window.update_idletasks()
        # Centra la finestra rispetto alla root
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()
        pos_x = root_x + (root_width // 2) - (win_width // 2)
        pos_y = root_y + (root_height // 2) - (win_height // 2)
        confirm_window.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")
        # Mostra la finestra solo dopo che è centrata
        confirm_window.deiconify()
        tk.Label(confirm_window, text=text, pady=20).pack()
        button_frame = tk.Frame(confirm_window)
        button_frame.pack(pady=5)
        return confirm_window, button_frame

    def confirm(self, title_window, text, task):
        confirm_window, button_frame = self.create_confirm_window(title_window, text)
        if task == "esci":
            tk.Button(button_frame, text="Si", width=10, command=self.stop).pack(side="left", padx=10)
        if task == "orienta":
            tk.Button(button_frame, text="Si", width=10, command=lambda: [self.orient_board(), confirm_window.destroy()]).pack(side="left", padx=10)
        tk.Button(button_frame, text="No", width=10, command=confirm_window.destroy).pack(side="right", padx=10)

    def count_moved_pieces(self, fen1, fen2):
        board1 = chess.Board(fen1)
        board2 = chess.Board(fen2)
        moved_pieces = 0
        for square in chess.SQUARES:
            piece1 = board1.piece_at(square)
            piece2 = board2.piece_at(square)
            if piece1 != None and piece1 != piece2:
                moved_pieces += 1
        return moved_pieces

    def switch_turn(self):
        self.turn = "w" if self.turn == "b" else "b"
        self.update_turn_label()

    def update_turn_label(self):
        if self.turn == "w":
            self.turn_label.config(text="Tocca al bianco")
        else:
            self.turn_label.config(text="Tocca al nero")

    def make_detection(self):
        self.automatic_detection = True
        self.recognize_move_loop(True)
        self.automatic_detection = False

    def recognize_move_loop(self, only_one_detection=False):
        if not self.running or not self.automatic_detection: 
            return
        try:
            self.turn = "w" if self.turn == "b" else "b"
            img = os.path.join("game_photos", f"photo{str(self.photo_number+1)}.png")
            txt = os.path.join("runs","detect",f"predict{str(self.photo_number+1)}","labels",f"photo{str(self.photo_number+1)}.txt")
            self.make_photo(img)
            model = YOLO("chesspiece-detection-model.pt")
            model.predict(source=img, save=True, save_txt=True)
            fen = extract_FEN(self.corners, img, txt)
            #se la posizione non è cambiata, oppure se da un riconoscimento all'altro ci sono stati più di 2 pezzi mossi, 
            #probabilmente significa che una mano sta passando sulla scacchiera nel momento della detection e sta coprendo molti pezzi
            #devo mettere > 2 perchè durante l'arrocco 2 pezzi cambiano posizione e finiscono in 2 case vuote (idem per le catture)
            #allo stesso tempo però per la detection forzata di una posizione (only_one_detection == True) potrei aver spostato volontariamente tanti pezzi
            #e quindi in quel caso non devo farmi bloccare dal fatto che i pezzi spostati sono > 2. Inoltre se dopo aver forzato la detection della posizione,
            #cambio nuovamente tanti pezzi attivando direttamente la detection automatica, questa detection non verrà accettata perchè magari ho modificato la posizione
            #di più di 4 pezzi, per questo motivo se si tratta della prima detection automatica dopo la detection forzata devo ignorare il controllo sui pezzi mossi usando first_automatic_detection
            if fen == self.old_fen or (self.count_moved_pieces(self.old_fen, fen) > 2 and not only_one_detection and not self.first_automatic_detection):
                #ripristinare il turno cambiato all'inizio della funzione che va ripristinato a quello vecchio
                self.turn = "w" if self.turn == "b" else "b"
            else:
                self.old_fen = fen
                self.update_turn_label()
                self.chessboard.set_fen(fen)
                self.update_board()
                if self.castling != "-":
                    self.manage_castle_rights()
            self.photo_number += 1
            self.first_automatic_detection = False
        except Exception as e:
            print(f"Errore durante il riconoscimento automatico: {e}")
        finally:
            if not only_one_detection:
                self.root.after(4000, self.recognize_move_loop) #Richiama se stessa dopo 4 secondi

    def orient_board(self):
        img = os.path.join("game_photos",f"photo{str(self.photo_number)}.png")
        txt = os.path.join("runs","detect","predict","labels",f"photo{str(self.photo_number)}.txt")
        self.make_photo(img)
        model = YOLO("modello.pt")
        model.predict(source=img, save=True, save_txt=True, conf=0.25, name="", exist_ok=True)
        self.corners = orient_chessboard(img, txt)

    def toggle_bounding_boxes(self):
        if self.bounding_boxes_state.get():
            self.show_bounding_boxes = True
        else:
            self.show_bounding_boxes = False

    def toggle_detection(self):
        if self.detection_state.get():
            self.automatic_detection = True
            self.instant_detection_button.config(state=tk.DISABLED)
            self.first_automatic_detection = True
            self.recognize_move_loop()
        else:
            self.automatic_detection = False
            self.instant_detection_button.config(state=tk.NORMAL)
            self.first_automatic_detection = False

    def make_photo(self, img_name):
        ret, frame = self.cap.read() 
        if not ret:
            print("Impossible to read the webcam")
            return
        original_height = frame.shape[0]
        original_width = frame.shape[1]
        taglio_alto = int(original_height * 0.25)  # elimina 25% della foto dall'alto
        taglio_destro = int(original_width * 0.13)  # 13% della foto da destra
        frame_cropped = frame[taglio_alto:, :original_width - taglio_destro]
        cv2.imwrite(img_name, frame_cropped)

    def initialize_stockfish(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        stockfish_path = os.path.join(base_dir, "Stockfish", "src", "stockfish")
        stockfish = Stockfish(stockfish_path, depth=15)
        stockfish.set_skill_level(20)
        return stockfish

    def get_stockfish_moves(self, number):
        best_moves = []
        fen_position = self.chessboard.board_fen()
        full_fen = f"{fen_position} {self.turn} {self.castling} - 0 1"
        self.stockfish.set_fen_position(full_fen)
        for move in self.stockfish.get_top_moves(number):
            if move["Mate"] is None:
                best_moves.append(f"{self.uci_to_text(move["Move"])}: Valutazione = {move["Centipawn"]/100}")
            else:
                best_moves.append(f"{self.uci_to_text(move["Move"])}: Matto in {abs(move["Mate"])} mosse")
        return best_moves
    
    def evaluate_move(self, move_uci):
        move = chess.Move.from_uci(move_uci)
        fen_position = self.chessboard.board_fen()
        full_fen = f"{fen_position} {self.turn} {self.castling} - 0 1"
        chessboard_copy = chess.Board(fen=full_fen)
        if move in chessboard_copy.legal_moves:
            chessboard_copy.push(move)
            fen_position = chessboard_copy.board_fen()
            turn = "w" if self.turn == "b" else "b"
            full_fen = f"{fen_position} {turn} {self.castling} - 0 1"
            self.stockfish.set_fen_position(full_fen)
            dict_evalutation = self.stockfish.get_evaluation()
            if dict_evalutation.get("type") == "cp":
                return f"Valutazione: {dict_evalutation['value']/100}"
            elif dict_evalutation.get("type") == "mate":
                return f"Matto in {abs(dict_evalutation['value'])} mosse"
        else:
            return "Mossa illegale nella posizione corrente"

    def stockfish_suggestions(self):
        best_moves = self.get_stockfish_moves(5)
        response = "Le 5 mosse migliori di stockfish sono:\n"
        for move in best_moves:
            response += f"{move}\n"
        self.add_message("Assistente", response)

    def get_all_widgets(self, parent):
        widgets = parent.winfo_children()
        for widget in widgets:
            widgets += self.get_all_widgets(widget)
        return widgets

    def set_cursor(self, cursor_type):
        for widget in self.get_all_widgets(self.root):
            try:
                widget.config(cursor=cursor_type)
            except tk.TclError:
                pass  # Alcuni widget potrebbero non supportare il cambio di cursore

    def handle_user_input(self, event=None):
        user_text = self.user_input.get()
        if user_text.strip() == "":
            return
        self.add_message("Utente", user_text)
        self.user_input.delete(0, tk.END)
        self.set_cursor("watch")
        self.root.update_idletasks()
        # Avvia un thread per non bloccare l'interfaccia
        threading.Thread(target=self.process_user_input, args=(user_text,), daemon=True).start()

    def process_user_input(self, user_text):
        if self.OPENAI_API_KEY:
            response = self.ask_chatGPT(user_text)
        elif self.GEMINI_API_KEY:
            response = self.ask_gemini(user_text)
        self.root.after(0, lambda: self.add_message("Assistente", response))
        self.root.after(0, lambda: self.set_cursor(""))

    def add_message(self, sender, message):
        self.chat_area.configure(state='normal')
        if sender == "Utente":
            self.chat_area.insert(tk.END, f"{sender}: ", "user_label")    # in blu
            self.chat_area.insert(tk.END, f"{message}\n", "user_message") # in arancione
        elif sender == "Assistente":
            self.chat_area.insert(tk.END, f"{sender}: ", "sender_label")  # in rosso
            self.chat_area.insert(tk.END, f"{message}\n", "assistant")    # in viola
        else:
            self.chat_area.insert(tk.END, f"{sender}: {message}\n")
        self.chat_area.configure(state='disabled')
        self.chat_area.yview(tk.END)

    def read_prompt(self, prompt_filename):
        filename = prompt_filename
        with open(filename, 'r', encoding='utf-8') as file:
            content = file.read()
        return content
    
    def ask_chatGPT(self, user_prompt):
        system_prompt = self.read_prompt("prompt_system.txt") #INFORMAZIONI DI CONTESTO DA DARE A CHATGPT (ad esempio sei un esperto di scacchi)
        client = OpenAI(api_key=self.OPENAI_API_KEY)
        stockfish_moves = self.get_stockfish_moves(5)
        color_turn = "white" if self.turn == "w" else "black"
        full_user_prompt = f"{user_prompt}\nToccal al {color_turn} e le mosse consigliate da stockfish con le rispettive valutazioni sono all'interno di questa lista: {stockfish_moves}"
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "evaluate_move",
                    "description": "Valuta una mossa in notazione UCI usando Stockfish nella posizione corrente",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "move_uci": {
                                "type": "string",
                                "description": "Mossa UCI da valutare (es: 'e2e4', 'g1f3')"
                            }
                        },
                        "required": ["move_uci"]
                    }
                }
            }
        ]
        completion = client.chat.completions.create(
            model = GPT_MODEL,
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_user_prompt}
            ],
            tools = tools,
            tool_choice = "auto",
            temperature=0.0
        )
        message = completion.choices[0].message
        if message.tool_calls:
            final_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_user_prompt},
                message
            ]
            for call in message.tool_calls:
                func_name = call.function.name
                args = json.loads(call.function.arguments)
                if func_name == "evaluate_move":
                    func_result = self.evaluate_move(args["move_uci"])
                    final_messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": func_name,
                        "content": func_result
                    })
            # Seconda richiesta: GPT riceve l'output della funzione
            followup = client.chat.completions.create(
                model=GPT_MODEL,
                messages=final_messages,
                temperature=0.0
            )
            return followup.choices[0].message.content
        # Altrimenti risponde direttamente
        return message.content.replace("\n", "")
        
    def uci_to_text(self, move_uci):
        square1 = move_uci[:2]
        square2 = move_uci[2:4]
        if self.square_to_piece(square2) != "casella":
            return f"Muovere {self.square_to_piece(square1)} che si trova in {square1} spostandolo/a in {square2} catturando {self.square_to_piece(square2)}"
        elif self.is_castle(square1, square2):
            return f"Muovere {self.square_to_piece(square1)} che si trova in {square1} spostandolo/a in {square2} facendo l'arrocco {self.castle_type}"
        return f"Muovere {self.square_to_piece(square1)} che si trova in {square1} spostandolo/a in {square2}"
    
    def ask_gemini(self, user_prompt):
        genai.configure(api_key=self.GEMINI_API_KEY)
        stockfish_moves = self.get_stockfish_moves(5)
        color_turn = "white" if self.turn == "w" else "black"
        system_prompt = self.read_prompt("prompt_system.txt") 
        full_user_prompt = f"{system_prompt}\n\n{user_prompt}\nTocca al {color_turn} e le mosse consigliate da Stockfish sono: {stockfish_moves}"
        gemini = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=system_prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.0)
        )
        evaluate_move_tool = genai.types.FunctionDeclaration(
            name="evaluate_move",
            description="Valuta una mossa in notazione UCI usando Stockfish nella posizione corrente",
            parameters={
                "type": "object",
                "properties": {
                    "move_uci": {
                        "type": "string",
                        "description": "Mossa UCI da valutare (es: 'e2e4', 'g1f3')"
                    }
                },
                "required": ["move_uci"]
            }
        )
        tools_list = [genai.types.Tool(function_declarations=[evaluate_move_tool])]
        # Inizio della cronologia della conversazione per Gemini
        # Il system_prompt è gestito a livello di modello.
        # Il primo messaggio è quello dell'utente.
        current_conversation_history = [
            glm.Content(role="user", parts=[glm.Part(text=full_user_prompt)])
        ]
        # Prima richiesta a Gemini
        response = gemini.generate_content(
            current_conversation_history,
            tools=tools_list
        )
        # Estrai la prima parte candidata della risposta
        candidate = response.candidates[0]
        message_part = candidate.content.parts[0] if candidate.content and candidate.content.parts else None
        if message_part and message_part.function_call:
            current_conversation_history.append(candidate.content)
            function_call = message_part.function_call
            func_name = function_call.name
            args = dict(function_call.args)
            if func_name == "evaluate_move":
                move_to_evaluate = args.get("move_uci")
                function_result_text = self.evaluate_move(move_to_evaluate)
                tool_response_part = glm.Part(
                    function_response=glm.FunctionResponse(
                        name=func_name,
                        response={"result": function_result_text}
                    )
                )
                current_conversation_history.append(glm.Content(role="function", parts=[tool_response_part]))
                # Seconda richiesta a Gemini con il risultato della funzione
                followup_response = gemini.generate_content(
                    current_conversation_history,
                    tools=tools_list
                )
                return followup_response.text.replace("\n", "")
            else:
                return f"Gemini: Richiesta chiamata a funzione sconosciuta: {func_name}"
        else:
            # Nessuna chiamata di funzione, il modello ha risposto direttamente, response.text dovrebbe contenere la risposta diretta
            return response.text.replace("\n", "")
        
    def square_to_piece(self, square):
        square = chess.parse_square(square)
        piece = self.chessboard.piece_at(square)
        if piece:
            return PIECES[piece.symbol()]
        else:
            return "casella"
                
    def is_castle(self, square1, square2):
        if self.square_to_piece(square1) == PIECES["K"] and square1 == "e1" and (square2 == "g1" or square2 == "c1"):
            self.castle_type = "corto" if square2 == "g1" else "lungo"
            return True
        if self.square_to_piece(square1) == PIECES["k"] and square1 == "e8" and (square2 == "g8" or square2 == "c8"):
            self.castle_type = "corto" if square2 == "g8" else "lungo"
            return True       
        return False

    #Controllare la posizione delle torri e dei re nella posizione rilevata per poter ottenere i diritti d'arrocco della posizione
    def manage_castle_rights(self):
        e1_piece = self.square_to_piece("e1")
        a1_piece = self.square_to_piece("a1")
        h1_piece = self.square_to_piece("h1")
        e8_piece = self.square_to_piece("e8")
        a8_piece = self.square_to_piece("a8")
        h8_piece = self.square_to_piece("h8")
        self.castling = ""
        valid_castle_conditions = [
            ("re bianco" in e1_piece and "torre bianca" in h1_piece, "K"),
            ("re bianco" in e1_piece and "torre bianca" in a1_piece, "Q"),
            ("re nero" in e8_piece and "torre nera" in h8_piece, "k"),
            ("re nero" in e8_piece and "torre nera" in a8_piece, "q"),
        ]
        for condition, letter in valid_castle_conditions:
            if condition and (letter not in self.castle_blacklist):
                self.castling += letter
            else:
                self.castle_blacklist.add(letter)
        if self.castling == "":
            self.castling = "-"

    def update_webcam(self):
        if not self.running:
            return
        ret, frame = self.cap.read()
        if ret:
            # Ritaglio (uguale a make_photo)
            original_height = frame.shape[0]
            original_width = frame.shape[1]
            taglio_alto = int(original_height * 0.3)
            taglio_destro = int(original_width * 0.13)
            frame_cropped = frame[taglio_alto:, :original_width - taglio_destro]
            # YOLOv8 prediction in real-time
            model = YOLO("modello.pt")
            results = model.predict(source=frame_cropped, conf=0.25, save=False, stream=True)
            if self.show_bounding_boxes:
                for r in results:
                    annotated_frame = r.plot() #Disegna bounding box
            else:
                annotated_frame = frame_cropped #Mostra solo il frame originale ritagliato
            # Visualizzazione
            cv2image = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(cv2image).resize((768, 576), Image.LANCZOS)
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.configure(image=imgtk)
        self.root.after(30, self.update_webcam) #programmare una chiamata futura alla funzione self.update_webcam dopo 30 millisecondi, all'interno del ciclo principale di Tkinter (mainloop).

    def update_board(self):
        svg_data = chess.svg.board(board=self.chessboard)
        png_data = cairosvg.svg2png(bytestring=svg_data)
        image = Image.open(io.BytesIO(png_data))
        image = image.resize((600, 600))
        tk_img = ImageTk.PhotoImage(image=image)
        self.chess_canvas.imgtk = tk_img
        self.chess_canvas.configure(image=tk_img)

    def stop(self):
        self.running = False
        self.cap.release()
        self.root.destroy()


def remove_files_in_folder(folder_path):
    if os.path.exists(folder_path):
        for filename in os.listdir(folder_path):
            full_path = os.path.join(folder_path, filename)
            if os.path.isfile(full_path):
                os.remove(full_path)
    else:
        os.makedirs(folder_path)

def remove_folder(folder_path):
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)

if __name__ == "__main__":
    load_dotenv(dotenv_path="keys.env")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not openai_api_key and not gemini_api_key:
        raise EnvironmentError("Devi impostare almeno una tra OPENAI_API_KEY e GEMINI_API_KEY nel file keys.env, nel caso in cui siano presenti entrambe la priorità sarà data a OPENAI_API_KEY")
    remove_files_in_folder("game_photos")
    remove_folder("runs")
    root = tk.Tk()
    if openai_api_key:
        app = ChessAssistantApp(root, openai_api_key, None)
    elif gemini_api_key:
        app = ChessAssistantApp(root, None, gemini_api_key)
    root.protocol("WM_DELETE_WINDOW", app.stop)
    root.mainloop()