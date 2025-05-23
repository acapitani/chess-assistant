from PIL import Image
import cv2
import numpy as np
from find_FEN import dict_to_fen

# Calcola dimensioni immagine
def get_image_dimensions(image_path):
    with Image.open(image_path) as img:
        width, height = img.size
    return width, height

# Trova i 4 angoli della scacchiera usando i pezzi di classe 1 e 7
def find_corners(image_path, file_path):
    corners = []
    with open(file_path, 'r') as file:
        lines = file.readlines()
    for line in lines:
        parts = line.strip().split()
        class_id = int(parts[0])
        if class_id in [1, 7]:
            x_center = float(parts[1])
            y_center = float(parts[2])
            height = float(parts[4])
            y_bottom = y_center + height / 2
            new_y = y_bottom - 0.2 * height
            image_width, image_height = get_image_dimensions(image_path)
            pixel_x = int(x_center * image_width)
            pixel_y = int(new_y * image_height)
            corners.append((pixel_x, pixel_y))
    return corners

# Orienta i 4 angoli nell'ordine corretto: a8, h8, h1, a1
def orient_chessboard(img_start, txt_start):
    corners = find_corners(img_start, txt_start)
    a1 = max(corners, key=lambda p: p[1])
    h1 = max(corners, key=lambda p: p[0])
    a8 = min(corners, key=lambda p: p[0])
    h8 = min(corners, key=lambda p: p[1])
    return [a8, h8, h1, a1]

# Calcola matrice di omografia e rettifica
def calcola_omografia(image_path, corners, output_size):
    img = cv2.imread(image_path)
    pts_src = np.array(corners, dtype=np.float32)
    w, h = output_size
    pts_dst = np.array([
        [0, 0],
        [w - 1, 0],
        [w - 1, h - 1],
        [0, h - 1]
    ], dtype=np.float32)
    H, _ = cv2.findHomography(pts_src, pts_dst)
    return H

# Converte coordinate trasformate in notazione algebrica (es: "e4")
def pixel_to_square(x, y, square_size=100):
    col = int(x // square_size)
    row = int(y // square_size)
    col = max(0, min(7, col))
    row = max(0, min(7, row))
    file = chr(ord('a') + col) # col 0 → 'a', col 7 → 'h'
    rank = str(8 - row)        # row 0 (in alto) → '8', row 7 (in basso) → '1'
    return file + rank

# Trova posizione di ogni pezzo in notazione scacchistica
def find_pieces_position(image_path, file_path, H):
    positions = []
    image_width, image_height = get_image_dimensions(image_path)
    with open(file_path, 'r') as file:
        for line in file:
            parts = line.strip().split()
            class_id = int(parts[0])
            x_center = float(parts[1])
            y_center = float(parts[2])
            height = float(parts[4])
            # Punto 20% sopra il fondo della bounding box
            y_bottom = y_center + height / 2
            new_y = y_bottom - 0.20 * height
            pixel_x = x_center * image_width
            pixel_y = new_y * image_height
            # Trasforma con omografia
            src_pt = np.array([[[pixel_x, pixel_y]]], dtype=np.float32)
            dst_pt = cv2.perspectiveTransform(src_pt, H)[0][0]
            # Converti a notazione scacchistica
            square = pixel_to_square(dst_pt[0], dst_pt[1])
            positions.append((class_id, square))
    return positions

def create_position_dictionary(positions):
    chessboard_dict = {}
    files = 'abcdefgh'
    ranks = '12345678'
    for f in files:
        for r in ranks:
            casella = f + r
            chessboard_dict[casella] = 12
    for class_id, square in positions:
        chessboard_dict[square] = class_id
    return chessboard_dict

def extract_FEN(corners, image_path, txt_path, turn, castling_options, halfmove_clock, fullmove_number, en_passant):
    H = calcola_omografia(image_path, corners, output_size=(800, 800))
    positions = find_pieces_position(image_path, txt_path, H)
    chessboard_dict = create_position_dictionary(positions)
    FEN = dict_to_fen(chessboard_dict, turn, castling_options, halfmove_clock, fullmove_number, en_passant)
    return FEN

def extract_FEN(corners, image_path, txt_path):
    H = calcola_omografia(image_path, corners, output_size=(800, 800))
    positions = find_pieces_position(image_path, txt_path, H)
    chessboard_dict = create_position_dictionary(positions)
    FEN = dict_to_fen(chessboard_dict)
    return FEN

if __name__ == "__main__":
    corners = orient_chessboard("foto_scattate_telecamera/photo33.png", "runs/detect/predict/labels/photo33.txt")
    numbers = ["33", "34", "35", "36"]
    for number in numbers:
        image_path = f"foto_scattate_telecamera/photo{number}.png"
        txt_path = f"runs/detect/predict/labels/photo{number}.txt"
        print(extract_FEN(corners, image_path, txt_path, "white", "KQkq"))