'''
--------------------------------------------------------
VARIABILE IN INPUT --> CASTLING
--------------------------------------------------------
"KQkq": (seleziona solo le lettere che ti servono)
 K = arrocco corto del bianco
 k = arrocco corto del nero
 Q = arrocco lungo del bianco
 q = arrocco lungo del nero
 "-": nessuno può arroccare (in entrambe le direzioni)
--------------------------------------------------------
VARIABILE IN INPUT --> TURN ("white" o "black")
--------------------------------------------------------
VARIABILE IN INPUT --> POSITION_DICT
--------------------------------------------------------
è un dizionario composto da 64 chiavi, ogni chiave
rappresenta una casella tramite la sua coordinata 
(ad esempio "e4", "c3", "a7" etc...)
Ogni valore associato alla chiave è un numero che
rappresenta il pezzo presente sulla casella.
In particolare le classi sono:
0 = pedone bianco 
1 = torre bianca
2 = cavallo bianco
3 = alfiere bianco
4 = regina bianca
5 = re bianco
6 = pedone nero
7 = torre nera
8 = cavallo nero
9 = alfiere nero
10 = regina nera
11 = re nero
12 = casella vuota
--------------------------------------------------------
'''
PIECE_MAP = {
    0: 'P', 1: 'R', 2: 'N', 3: 'B', 4: 'Q', 5: 'K',
    6: 'p', 7: 'r', 8: 'n', 9: 'b', 10: 'q', 11: 'k',
    12: None  # casella vuota
}
def dict_to_fen(position_dict, turn, castling_options, halfmove_clock, fullmove_number, en_passant):
    fen_rows = []
    # Costruzione riga per riga (dalla 8 alla 1)
    for rank in range(8, 0, -1):
        row = ''
        empty_count = 0
        for file in 'abcdefgh':
            square = f'{file}{rank}'
            value = position_dict.get(square, 12)  # default a casella vuota
            symbol = PIECE_MAP[value]
            if symbol is None:
                empty_count += 1
            else:
                if empty_count > 0:
                    row += str(empty_count)
                    empty_count = 0
                row += symbol
        if empty_count > 0:
            row += str(empty_count)
        fen_rows.append(row)
    fen_board = '/'.join(fen_rows)
    fen_turn = 'w' if turn.lower() == 'white' else 'b'
    full_fen = f"{fen_board} {fen_turn} {castling_options} {en_passant} {str(halfmove_clock)} {str(fullmove_number)}"
    return full_fen

def dict_to_fen(position_dict):
    fen_rows = []
    for rank in range(8, 0, -1):
        row = ''
        empty_count = 0
        for file in 'abcdefgh':
            square = f'{file}{rank}'
            value = position_dict.get(square, 12)  # default a casella vuota
            symbol = PIECE_MAP[value]
            if symbol is None:
                empty_count += 1
            else:
                if empty_count > 0:
                    row += str(empty_count)
                    empty_count = 0
                row += symbol
        if empty_count > 0:
            row += str(empty_count)
        fen_rows.append(row)
    fen_board = '/'.join(fen_rows)
    return fen_board