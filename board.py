import regex as re
import copy

class BoardParams:
    def __init__(self, board_def):
        board_lines = board_def.strip().split('\n')
        self.num_rows, self.num_cols = map(int, board_lines[0].split(','))
        self.start_row, self.start_col = map(int, board_lines[1].split(','))
        self.special_tiles = {}
        self.num_special_tiles = int(board_lines[2])
        for i in range(3, 3 + self.num_special_tiles):
            row, col, tile_type = board_lines[i].split(',')
            self.special_tiles[(int(row), int(col))] = tile_type

class Square:
    # default behavior is blank square, no score modifier, all cross-checks valid
    def __init__(self, letter=None, modifier="Normal", sentinel=1):
        self.letter = letter
        self.cross_checks_0 = [sentinel] * 26
        self.cross_checks_1 = [sentinel] * 26
        self.cross_checks = self.cross_checks_0
        self.modifier = modifier
        self.visible = True
        if sentinel == 0:
            self.visible = False

    def __str__(self):
        if not self.visible:
            return ""
        if not self.letter:
            return "_"
        else:
            return self.letter

    # maintain two separate cross-check lists depending on if the board is transpose or not
    def check_switch(self, is_transpose):
        if is_transpose:
            self.cross_checks = self.cross_checks_1
        else:
            self.cross_checks = self.cross_checks_0


class ScrabbleBoard:
    def __init__(self, dawg_root, board_params):

        self.board_params = board_params
        self.board = []
        for row in range(self.board_params.num_rows):
            row_list = []
            for col in range(self.board_params.num_cols):
                row_list.append(Square())
            self.board.append(row_list)

        self.point_dict = {'A': 1, 'B': 3, 'C': 3, 'D': 2, 'E': 1, 'F': 4, 'G': 2,
                     'H': 4, 'I': 1, 'J': 8, 'K': 5, 'L': 1, 'M': 3,
                     'N': 1, 'O': 1, 'P': 3, 'Q': 10, 'R': 1, 'S': 1, 'T': 1,
                     'U': 1, 'V': 4, 'W': 4, 'X': 8, 'Y': 4, 'Z': 10};

        self.words_on_board = []

        self.is_transpose = False

        # variables to encode best word on a given turn
        self.dawg_root = dawg_root
        self.word_rack = []
        self.word_score_dict = {}
        self.best_word = ""
        self.highest_score = 0
        self.dist_from_anchor = 0
        self.letters_from_rack = []

        # rows and columns of highest-scoring word found so far.
        # these are the rows and columns of the tile already on the board
        self.best_row = 0
        self.best_col = 0

        # store squares that need updated cross-checks
        self.upper_cross_check = []
        self.lower_cross_check = []

    # transpose method that modifies self.board inplace
    def _transpose(self):
        # https://datagy.io/python-transpose-list-of-lists/
        transposed_tuples = copy.deepcopy(list(zip(*self.board)))
        self.board = [list(sublist) for sublist in transposed_tuples]
        self.is_transpose = not self.is_transpose

    # TODO: fix scoring errors
    def _score_word(self, word, squares, dist_from_anchor):
        score = 0
        score_multiplier = 1

        if self.is_transpose:
            cross_sum_ind = "-"
        else:
            cross_sum_ind = "+"

        # word that will be inserted onto board shouldn't have wildcard indicator
        board_word = word.replace("%", "")

        # don't add words that are already on the board
        if board_word in self.words_on_board:
            return board_word, 0

        # remove letters before wildcard indicators
        word = re.sub("[A-Z]%", "%", word)

        # maintain list of which tiles were pulled from word rack
        rack_tiles = []
        for letter, square in zip(word, squares):
            # add cross-sum by adding first and second letter scores from orthogonal two-letter word
            if cross_sum_ind in square.modifier:
                score += int(square.modifier[-1])
            if square.modifier:
                rack_tiles.append(letter)
            if "2LS" in square.modifier:
                score += (self.point_dict[letter] * 2)
            elif "3LS" in square.modifier:
                score += (self.point_dict[letter] * 3)
            elif "2WS" in square.modifier:
                score_multiplier *= 2
                score += self.point_dict[letter]
            elif "3WS" in square.modifier:
                score_multiplier *= 3
                score += self.point_dict[letter]
            else:
                score += self.point_dict[letter]

        score *= score_multiplier

        # check for bingo
        if len(rack_tiles) == 7:
            score += 50

        if score > self.highest_score:
            self.best_word = board_word
            self.highest_score = score
            # distance of leftmost placed tile from anchor. if anchor is leftmost tile distance will be 0.
            self.dist_from_anchor = dist_from_anchor
            self.letters_from_rack = rack_tiles

    def _extend_right(self, start_node, square_row, square_col, rack, word, squares, dist_from_anchor):
        square = self.board[square_row][square_col]
        square.check_switch(self.is_transpose)

        # execute if square is empty
        if not square.letter:
            if start_node.is_terminal:
                self._score_word(word, squares, dist_from_anchor)
            for letter in start_node.children:
                # if square already has letters above and below it, don't try to extend
                if (square_row + 1 <= self.board_params.num_rows - 1) and\
                        self.board[square_row + 1][square_col].letter and \
                        (square_row - 1 >= 0) and\
                        self.board[square_row - 1][square_col].letter:
                    continue

                # conditional for blank squares
                if letter in rack:
                    wildcard = False
                elif "%" in rack:
                    wildcard = True
                else:
                    continue
                if letter in rack and self._cross_check(letter, square):
                    new_node = start_node.children[letter]
                    new_rack = rack.copy()
                    if wildcard:
                        new_word = word + letter + "%"
                        new_rack.remove("%")
                    else:
                        new_word = word + letter
                        new_rack.remove(letter)
                    new_squares = squares + [square]
                    if square_col + 1 == self.board_params.num_cols:
                        return
                    self._extend_right(new_node, square_row, square_col + 1, new_rack, new_word, new_squares,
                                       dist_from_anchor)
        else:
            if square_col + 1 == self.board_params.num_cols:
                return
            if square.letter in start_node.children:
                new_node = start_node.children[square.letter]
                new_word = word + square.letter
                new_squares = squares + [square]
                self._extend_right(new_node, square_row, square_col + 1, rack, new_word, new_squares,
                                   dist_from_anchor)

    def _left_part(self, start_node, anchor_square_row, anchor_square_col, rack, word, squares, limit,
                   dist_from_anchor):
        potential_square = self.board[anchor_square_row][anchor_square_col - dist_from_anchor]
        potential_square.check_switch(self.is_transpose)
        if potential_square.letter:
            return
        self._extend_right(start_node, anchor_square_row, anchor_square_col, rack, word, squares, dist_from_anchor)
        if 0 in potential_square.cross_checks:
            return
        if limit > 0:
            for letter in start_node.children:
                # conditional for blank squares
                if letter in rack:
                    wildcard = False
                elif "%" in rack:
                    wildcard = True
                else:
                    continue

                new_node = start_node.children[letter]
                new_rack = rack.copy()
                if wildcard:
                    new_word = word + letter + "%"
                    new_rack.remove("%")
                else:
                    new_word = word + letter
                    new_rack.remove(letter)
                new_squares = squares + [potential_square]
                self._left_part(new_node, anchor_square_row, anchor_square_col, new_rack, new_word, new_squares,
                                limit - 1, dist_from_anchor + 1)

    def _update_cross_checks(self):
        while self.upper_cross_check:
            curr_square, lower_letter, lower_row, lower_col = self.upper_cross_check.pop()
            curr_square.check_switch(self.is_transpose)

            # add to modifier for computing cross-sum
            if self.is_transpose:
                curr_square.modifier += f"-{self.point_dict[lower_letter]}"
            else:
                curr_square.modifier += f"+{self.point_dict[lower_letter]}"

            chr_val = 65
            # prevent cross stacking deeper than 2 layers
            if curr_square.letter:
                if not self.is_transpose:
                    self.board[lower_row - 2][lower_col].cross_checks_0 = [0] * 26
                    self.board[lower_row + 1][lower_col].cross_checks_0 = [0] * 26

                else:
                    self.board[lower_row - 2][lower_col].cross_checks_1 = [0] * 26
                    self.board[lower_row + 1][lower_col].cross_checks_1 = [0] * 26
                continue

            for i, ind in enumerate(curr_square.cross_checks):
                if ind == 1:
                    test_node = self.dawg_root.children[chr(chr_val)]
                    if (lower_letter not in test_node.children) or (not test_node.children[lower_letter].is_terminal):
                        curr_square.cross_checks[i] = 0
                chr_val += 1

        while self.lower_cross_check:
            curr_square, upper_letter, upper_row, upper_col = self.lower_cross_check.pop()
            curr_square.check_switch(self.is_transpose)

            # add to modifier for computing cross-sum
            if self.is_transpose:
                curr_square.modifier += f"-{self.point_dict[upper_letter]}"
            else:
                curr_square.modifier += f"+{self.point_dict[upper_letter]}"

            chr_val = 65
            # prevent cross stacking deeper than 2 layers
            if curr_square.letter:
                if not self.is_transpose:
                    self.board[upper_row - 1][upper_col].cross_checks_0 = [0] * 26
                    self.board[upper_row + 2][upper_col].cross_checks_0 = [0] * 26
                else:
                    self.board[upper_row - 1][upper_col].cross_checks_1 = [0] * 26
                    self.board[upper_row + 2][upper_col].cross_checks_1 = [0] * 26
                continue

            for i, ind in enumerate(curr_square.cross_checks):
                if ind == 1:
                    test_node = self.dawg_root.children[upper_letter]
                    if (chr(chr_val) not in test_node.children) or (not test_node.children[chr(chr_val)].is_terminal):
                        curr_square.cross_checks[i] = 0
                chr_val += 1

    def _cross_check(self, letter, square):
        square.check_switch(self.is_transpose)
        chr_val = 65
        for i, ind in enumerate(square.cross_checks):
            if ind == 1:
                if chr(chr_val) == letter:
                    return True
            chr_val += 1
        return False

    def print_board(self):
        print("    ", end="")
        [print(str(num).zfill(2), end=" ") for num in range(1, self.board_params.num_cols+1)]
        print()
        for i, row in enumerate(self.board):
            if i != self.board_params.num_rows:
                print(str(i + 1).zfill(2), end="  ")
            [print(square, end="  ") for square in row]
            print()
        print()

    # method to insert words into board by row and column number
    # using 1-based indexing for user input
    def insert_word(self, row, col, word):
        row -= 1
        col -= 1
        if len(word) + col > self.board_params.num_cols:
            print(f'Cannot insert word "{word}" at column {col + 1}, '
                  f'row {row + 1} not enough space')
            return
        curr_col = col
        modifiers = []
        for i, letter in enumerate(word):
            curr_square_letter = self.board[row][curr_col].letter
            modifiers.append(self.board[row][curr_col].modifier)
            # if current square already has a letter in it, check to see if it's the same letter as
            # the one we're trying to insert. If not, insertion fails, undo any previous insertions
            if curr_square_letter:
                if curr_square_letter == letter:
                    if row > 0:
                        self.upper_cross_check.append((self.board[row - 1][curr_col], letter, row, curr_col))
                    if row < self.board_params.num_rows:
                        self.lower_cross_check.append((self.board[row + 1][curr_col], letter, row, curr_col))

                    curr_col += 1
                else:
                    print(f'Failed to insert letter "{letter}" of "{word}" at column {curr_col + 1}, '
                          f'row {row + 1}. Square is occupied by letter "{curr_square_letter}"')
                    self.upper_cross_check = []
                    self.lower_cross_check = []
                    for _ in range(i):
                        curr_col -= 1
                        self.board[row][curr_col].letter = None
                        self.board[row][curr_col].modifier = modifiers.pop()
                    return
            else:
                self.board[row][curr_col].letter = letter

                # reset any modifiers to 0 once they have a tile placed on top of them
                self.board[row][curr_col].modifier = ""

                # once letter is inserted, add squares above and below it to cross_check_queue
                if row > 0:
                    self.upper_cross_check.append((self.board[row - 1][curr_col], letter, row, curr_col))
                if row < self.board_params.num_rows:
                    self.lower_cross_check.append((self.board[row + 1][curr_col], letter, row, curr_col))

                curr_col += 1

        # place 0 cross-check sentinel at the beginning and end of inserted words to stop accidental overlap.
        # sentinels should only be for the board state opposite from the one the board is currently in
        if curr_col < self.board_params.num_cols:
            if self.is_transpose:
                self.board[self.best_row][curr_col].cross_checks_0 = [0] * 26
            else:
                self.board[self.best_row][curr_col].cross_checks_1 = [0] * 26
        if col - 1 > - 1:
            if self.is_transpose:
                self.board[self.best_row][col - 1].cross_checks_0 = [0] * 26
            else:
                self.board[self.best_row][col - 1].cross_checks_1 = [0] * 26

        # TODO: disable for now
        #self._update_cross_checks()

        self.words_on_board.append(word)

    # gets all words that can be made using a selected filled square and the current word rack
    def get_all_words(self, square_row, square_col, rack):
        square_row -= 1
        square_col -= 1

        # get all words that start with the filled letter
        self._extend_right(self.dawg_root, square_row, square_col, rack, "", [], 0)

        # create anchor square only if the space is empty
        if self.board[square_row][square_col - 1].letter:
            return

        # try every letter in rack as possible anchor square
        for i, letter in enumerate(rack):
            # Only allow anchor square with trivial cross-checks
            potential_square = self.board[square_row][square_col - 1]
            potential_square.check_switch(self.is_transpose)
            if 0 in potential_square.cross_checks or potential_square.letter:
                continue
            temp_rack = rack[:i] + rack[i + 1:]
            self.board[square_row][square_col - 1].letter = letter
            self._left_part(self.dawg_root, square_row, square_col - 1, temp_rack, "", [], 6, 1)

        # reset anchor square spot to blank after trying all combinations
        self.board[square_row][square_col - 1].letter = None

    # scan all tiles on board in both transposed and non-transposed state, find best move
    def get_best_move(self, word_rack):

        self.word_rack = word_rack

        # clear out cross-check lists before adding new words
        # TODO: disable for now
        #self._update_cross_checks()

        # reset word variables to clear out words from previous turns
        self.best_word = ""
        self.highest_score = 0
        self.best_row = 0
        self.best_col = 0

        transposed = False
        for row in range(0, self.board_params.num_rows):
            for col in range(0, self.board_params.num_cols):
                curr_square = self.board[row][col]
                if curr_square.letter and (not self.board[row][col - 1].letter):
                    prev_best_score = self.highest_score
                    self.get_all_words(row + 1, col + 1, word_rack)
                    if self.highest_score > prev_best_score:
                        self.best_row = row
                        self.best_col = col

        self._transpose()
        for row in range(0, self.board_params.num_rows):
            for col in range(0, self.board_params.num_cols):
                curr_square = self.board[row][col]
                if curr_square.letter and (not self.board[row][col - 1].letter):
                    prev_best_score = self.highest_score
                    # TODO: looks strange, why +1 on row? is it a variant on the game?
                    self.get_all_words(row + 1, col + 1, word_rack)
                    if self.highest_score > prev_best_score:
                        transposed = True
                        self.best_row = row
                        self.best_col = col

        # Don't try to insert word if we couldn't find one
        if not self.best_word:
            self._transpose()
            return word_rack

        if transposed:
            self.insert_word(self.best_row + 1, self.best_col + 1 - self.dist_from_anchor, self.best_word)
            self._transpose()
        else:
            self._transpose()
            self.insert_word(self.best_row + 1, self.best_col + 1 - self.dist_from_anchor, self.best_word)

        self.word_score_dict[self.best_word] = self.highest_score

        for letter in self.letters_from_rack:
            if letter in word_rack:
                word_rack.remove(letter)

        return word_rack

    def get_start_move(self, word_rack):
        # board symmetrical at start so just always play the start move horizontally
        # try every letter in rack as possible anchor square
        # TODO: get if from board params
        self.best_row = int(self.board_params.num_rows/2)
        self.best_col = int(self.board_params.num_cols/2) + 1
        for i, letter in enumerate(word_rack):
            potential_square = self.board[self.best_row][self.best_col]
            temp_rack = word_rack[:i] + word_rack[i + 1:]
            potential_square.letter = letter
            self._left_part(self.dawg_root, self.best_row, self.best_col, temp_rack, "", [], self.best_col-2, 1)

        # reset anchor square spot to blank after trying all combinations
        self.board[self.best_row][self.best_col].letter = None
        self.insert_word(self.best_row + 1, self.best_col + 1 - self.dist_from_anchor, self.best_word)
        self.board[self.best_row][self.best_col].modifier = ""
        self.word_score_dict[self.best_word] = self.highest_score

        for letter in self.letters_from_rack:
            if letter in word_rack:
                word_rack.remove(letter)

        return word_rack






