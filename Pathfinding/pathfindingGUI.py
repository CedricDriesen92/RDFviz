import json
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, LinearSegmentedColormap
import heapq
from matplotlib.widgets import Button, Slider, TextBox, RadioButtons, CheckButtons
import tkinter as tk
from tkinter.filedialog import askopenfilename
from scipy.interpolate import griddata
import time

tk.Tk().withdraw()  # part of the import if you are not using other tkinter functions
from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
import warnings

warnings.filterwarnings("ignore")


class Node:
    def __init__(self, position, g=0, h=0):
        self.position = position
        self.g = g
        self.h = h
        self.f = g + h
        self.parent = None

    def __lt__(self, other):
        return self.f < other.f


class InteractiveBIMPathfinder:
    def __init__(self, filename):
        self.grids, self.bbox, self.floors, self.grid_size = self.load_grid_data(filename)
        self.start = None
        self.goals = []
        self.grid_stairs = None
        self.current_floor = 0
        self.speed = 1  # Default speed
        self.fig, self.ax = plt.subplots(figsize=(12, 9))
        self.canvas = self.fig.canvas
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.fig.canvas.get_tk_widget().master)
        self.toolbar.update()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)
        self.dragging = None
        self.fig.canvas.mpl_connect('button_press_event', self.on_press)
        self.fig.canvas.mpl_connect('button_release_event', self.on_release)
        self.fig.canvas.mpl_connect('motion_notify_event', self.on_motion)

        self.path = None
        self.pathlength = None
        self.minimize_cost = True
        self.algorithm = 'A*'
        self.animated = True
        self.fps = 1
        self.heuristic_style = 'Min'
        self.show_heuristic = False
        self.heuristic_resolution = 10
        self.allow_diagonal = True
        self.wall_buffer = 0
        self.buffered_grids = None
        self.background = None
        self.artists = []
        self.setup_plot()
        self.json_filename = filename

    def load_grid_data(self, filename):
        with open(filename, 'r') as f:
            data = json.load(f)
        grids = [np.array(grid) for grid in data['grids']]
        return grids, data['bbox'], data['floors'], data['grid_size']

    def setup_plot(self):
        plt.subplots_adjust(bottom=0.3)
        self.ax_prev = plt.axes([0.2, 0.15, 0.1, 0.075])
        self.ax_next = plt.axes([0.31, 0.15, 0.1, 0.075])
        self.ax_start = plt.axes([0.42, 0.15, 0.1, 0.075])
        self.ax_goal = plt.axes([0.53, 0.15, 0.1, 0.075])
        self.ax_run = plt.axes([0.64, 0.15, 0.1, 0.075])
        #self.ax_speed = plt.axes([0.2, 0.05, 0.6, 0.03])
        self.ax_pathlength = plt.axes([0.9, 0.15, 0.075, 0.03])
        self.ax.set_xlim(0, self.grids[0].shape[1])
        self.ax.set_ylim(0, self.grids[0].shape[0])
        self.ax_minimize = plt.axes([0.75, 0.3, 0.2, 0.1])
        self.ax_fps = plt.axes([0.75, 0.65, 0.2, 0.03])

        self.b_prev = Button(self.ax_prev, 'Previous')
        self.b_next = Button(self.ax_next, 'Next')
        self.b_start = Button(self.ax_start, 'Set Start')
        self.b_goal = Button(self.ax_goal, 'Set Goal')
        self.b_run = Button(self.ax_run, 'Run A*')
        #self.s_speed = Slider(self.ax_speed, 'Delay', 1, 100, valinit=self.speed, valstep=0.1)
        self.t_pathlength = TextBox(self.ax_pathlength, 'Path Length:', initial='0')
        self.radio_minimize = RadioButtons(self.ax_minimize, ('Cost', 'Distance'))
        self.s_fps = Slider(self.ax_fps, 'fps', 0.1, 5, valinit=self.fps, valstep=0.1)

        self.b_prev.on_clicked(self.prev_floor)
        self.b_next.on_clicked(self.next_floor)
        self.b_start.on_clicked(self.set_start_mode)
        self.b_goal.on_clicked(self.set_goal_mode)
        self.b_run.on_clicked(self.run_algorithm)
        #self.s_speed.on_changed(self.update_speed)
        self.radio_minimize.on_clicked(self.set_minimize)
        self.s_fps.on_changed(self.update_fps)

        self.ax_heuristic = plt.axes([0.75, 0.5, 0.2, 0.05])
        self.b_heuristic = Button(self.ax_heuristic, 'Toggle Heuristic')
        self.b_heuristic.on_clicked(self.toggle_heuristic)

        self.ax_heuristic_style = plt.axes([0.75, 0.4, 0.2, 0.1])
        self.radio_heuristic_style = RadioButtons(self.ax_heuristic_style, ('Min', 'Sum'))
        self.radio_heuristic_style.on_clicked(self.set_heuristic_style)

        self.ax_diagonal = plt.axes([0.75, 0.25, 0.2, 0.05])
        self.check_diagonal = CheckButtons(self.ax_diagonal, ['Allow Diagonal'], [self.allow_diagonal])
        self.check_diagonal.on_clicked(self.toggle_diagonal)

        self.ax_animate = plt.axes([0.75, 0.7, 0.2, 0.05])
        self.check_animate = CheckButtons(self.ax_animate, ['Animate'], [self.animated])
        self.check_animate.on_clicked(self.toggle_animation)

        self.ax_identify_exits = plt.axes([0.75, 0.55, 0.2, 0.05])
        self.b_identify_exits = Button(self.ax_identify_exits, 'Identify Exits')
        self.b_identify_exits.on_clicked(self.identify_exits)

        self.ax_buffer = plt.axes([0.75, 0.6, 0.2, 0.03])
        self.s_buffer = Slider(self.ax_buffer, 'Wall Buffer', 0, self.grid_size*10, valinit=0, valstep=self.grid_size)
        self.s_buffer.on_changed(self.update_buffer)

        self.mode = None
        #self.fig.canvas.mpl_connect('button_press_event', self.on_click)
        self.fig.canvas.mpl_connect('draw_event', self.on_draw)
        self.apply_wall_buffer()
        self.update_plot()

    def on_press(self, event):
        self.background = None
        if event.inaxes != self.ax:
            return
        x, y = int(event.xdata), int(event.ydata)

        # Check if clicking on start point
        if self.start and abs(x - self.start[0]) <= 1 and abs(y - self.start[1]) <= 1 and self.current_floor == \
                self.start[2]:
            self.dragging = 'start'
            return

        # Check if clicking on a goal point
        for i, goal in enumerate(self.goals):
            if abs(x - goal[0]) <= 1 and abs(y - goal[1]) <= 1 and self.current_floor == goal[2]:
                if event.button == 1:  # Left click to drag
                    self.dragging = ('goal', i)
                elif event.button == 3:  # Right click to delete
                    self.goals.pop(i)
                    self.update_plot()
                return

        # If not clicking on existing points, add new start/goal
        if self.mode == 'start':
            self.start = (x, y, self.current_floor)
            print(f"Start set to: {self.start}")
        elif self.mode == 'goal':
            new_goal = (x, y, self.current_floor)
            self.goals.append(new_goal)
            print(f"Goal added: {new_goal}")
        self.mode = None
        self.update_plot()

    def on_release(self, event):
        self.background = None
        self.dragging = None

    def on_motion(self, event):
        if self.dragging and event.inaxes == self.ax:
            self.background = None
            x, y = int(event.xdata), int(event.ydata)
            if self.dragging == 'start':
                self.start = (x, y, self.current_floor)
            elif self.dragging[0] == 'goal':
                i = self.dragging[1]
                self.goals[i] = (x, y, self.current_floor)
            self.update_plot()

    def on_draw(self, event):
        self.background = self.fig.canvas.copy_from_bbox(self.ax.bbox)
        self.draw_animated_artists()

    def draw_animated_artists(self):
        for artist in self.artists:
            try:
                if isinstance(artist, plt.Text):
                    # For Text artists, check if axes are valid
                    if artist.axes is not None and artist.axes.transData is not None:
                        self.ax.draw_artist(artist)
                else:
                    self.ax.draw_artist(artist)
            except AttributeError:
                # Ignore AttributeError, which might occur if axes are not ready
                pass
        self.fig.canvas.blit(self.ax.bbox)

    def set_algorithm(self, label):
        self.algorithm = label

    def set_minimize(self, label):
        self.minimize_cost = (label == 'Cost')

    def toggle_animation(self, label):
        self.animated = not self.animated

    def set_heuristic_style(self, label):
        self.heuristic_style = label.lower()
        if self.show_heuristic:
            self.calculate_sparse_heuristic()
            self.update_plot()

    def toggle_diagonal(self, label):
        self.allow_diagonal = not self.allow_diagonal

    def update_speed(self, val):
        self.speed = int(val)

    def update_fps(self, val):
        self.fps = float(val)

    def update_buffer(self, val):
        self.wall_buffer = val
        self.apply_wall_buffer()
        self.background = None
        self.update_plot()

    def apply_wall_buffer(self):
        self.buffered_grids = []
        for floor in self.grids:
            buffered_floor = floor.copy()
            #print(floor[0:10, 0:3])
            wall_mask = (floor == 'wall')

            buffer_distance = int(self.wall_buffer / self.grid_size)

            for _ in range(buffer_distance):
                wall_mask = self.expand_mask(wall_mask)
            rows, cols = wall_mask.shape
            for i in range(rows):
                for j in range(cols):
                    if wall_mask[i, j] and floor[i,j] not in ['wall', 'door', 'stair']:
                        buffered_floor[i,j] = 'walla'
            self.buffered_grids.append(buffered_floor)
            #print(buffered_floor[0:10, 0:3])

    def expand_mask(self, mask):
        expanded = mask.copy()
        rows, cols = mask.shape
        for i in range(rows):
            for j in range(cols):
                if mask[i, j]:
                    for di in [-1, 0, 1]:
                        for dj in [-1, 0, 1]:
                            if 0 <= i + di < rows and 0 <= j + dj < cols:
                                expanded[i + di, j + dj] = True
        return expanded

    def grid_to_numeric(self, grid):
        element_types = ['empty', 'wall', 'door', 'stair', 'floor', 'walla']
        numeric_grid = np.zeros_like(grid, dtype=int)
        for i, element_type in enumerate(element_types):
            numeric_grid[grid == element_type] = i
        return numeric_grid

    def toggle_heuristic(self, event):
        self.show_heuristic = not self.show_heuristic
        self.background = None
        self.update_plot()
        self.draw_animated_artists()

    def prev_floor(self, event):
        if self.current_floor > 0:
            self.current_floor -= 1
            self.background = None  # Reset background to force full redraw
            self.update_plot()

    def next_floor(self, event):
        if self.current_floor < len(self.grids) - 1:
            self.current_floor += 1
            self.background = None  # Reset background to force full redraw
            self.update_plot()

    def set_start_mode(self, event):
        self.mode = 'start'

    def set_goal_mode(self, event):
        self.mode = 'goal'

    def identify_exits(self, event):
        exits = set()
        for floor_index, floor in enumerate(self.grids):
            rows, cols = floor.shape
            for i in range(rows):
                for j in range(cols):
                    if floor[i, j] == 'door':
                        if self.is_exit(floor, i, j):
                            exits.add((i, j, floor_index))

        # Filter exits to keep only one per BIM door
        filtered_exits = self.filter_exits(exits)

        # Add filtered exits as goals
        for exit in filtered_exits:
            if exit not in self.goals:
                self.goals.append(exit)

        self.update_plot()

    def is_exit(self, floor, x, y):
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]
        rows, cols = floor.shape

        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            while 0 <= nx < rows and 0 <= ny < cols:
                if floor[nx, ny] in ['wall', 'door']:
                    break
                if nx == 0 or nx == rows - 1 or ny == 0 or ny == cols - 1:
                    return True
                nx, ny = nx + dx, ny + dy

        return False

    def filter_exits(self, exits):
        filtered = set()
        for exit in exits:
            if not any(self.are_connected_by_doors(exit, existing) for existing in filtered):
                filtered.add(exit)
        return filtered

    def are_connected_by_doors(self, pos1, pos2):
        if pos1[2] != pos2[2]:  # Different floors
            return False

        floor = self.grids[pos1[2]]
        visited = set()
        queue = [pos1[:2]]

        while queue:
            x, y = queue.pop(0)
            if (x, y) == pos2[:2]:
                return True

            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                nx, ny = x + dx, y + dy
                if (nx, ny) not in visited and floor[nx, ny] == 'door':
                    visited.add((nx, ny))
                    queue.append((nx, ny))

        return False

    def update_plot(self):
        if self.background is None:
            self.ax.clear()
            if self.wall_buffer > 0:
                colors = ['white', 'black', 'orange', 'red', 'lavenderblush', 'lightgray']
                color_map = ListedColormap(colors)
                grid = self.grid_to_numeric(self.buffered_grids[self.current_floor])
            else:
                colors = ['white', 'black', 'orange', 'red', 'lavenderblush']
                color_map = ListedColormap(colors)
                grid = self.grid_to_numeric(self.grids[self.current_floor])

            self.ax.imshow(grid.T, cmap=color_map, interpolation='nearest')

            if self.show_heuristic and self.goals:
                heuristic_map = self.calculate_sparse_heuristic()
                if heuristic_map is not None:
                    heuristic_cmap = LinearSegmentedColormap.from_list("", ["blue", "green", "yellow", "red"])
                    self.ax.imshow(heuristic_map.T, cmap=heuristic_cmap, alpha=0.5)

            # Update only dynamic elements
            if self.start and self.start[2] == self.current_floor:
                start_point, = self.ax.plot(self.start[0], self.start[1], 'go', markersize=10, label='Start')

            for i, goal in enumerate(self.goals):
                if goal[2] == self.current_floor:
                    goal_point, = self.ax.plot(goal[0], goal[1], 'ro', markersize=10)
                    text = self.ax.annotate(str(i + 1), (goal[0], goal[1]), color='white', ha='center', va='center')

            if self.path:
                path_on_floor = [node for node in self.path if node[2] == self.current_floor]
                for i in range(len(path_on_floor) - 1):
                    start = path_on_floor[i]
                    end = path_on_floor[i + 1]

                    # Check if this segment is continuous or a jump
                    if (abs(end[0] - start[0]) > 1 or abs(end[1] - start[1]) > 1):
                        # Discontinuous segment - draw in green
                        self.ax.plot([start[0], end[0]], [start[1], end[1]], color='green', linewidth=2, linestyle='--')
                    else:
                        # Continuous segment - draw in blue
                        self.ax.plot([start[0], end[0]], [start[1], end[1]], color='blue', linewidth=2)

            self.ax.set_title(f'Floor {self.current_floor + 1}')
            self.ax.axis('off')

            self.fig.canvas.draw()
            self.background = self.fig.canvas.copy_from_bbox(self.ax.bbox)
        else:
            self.fig.canvas.restore_region(self.background)

        for artist in self.artists:
            artist.remove()
        self.artists.clear()

    def find_all_stairs(self):
        grid_stairs = []
        #print(self.grids)
        for z in range(len(self.grids)):
            for i in range(self.grids[z].shape[0]):
                for j in range(self.grids[z].shape[1]):
                    #print(str(z), " ", str(i), " ", str(j))
                    if self.grids[z][i, j] == 'stair':
                        grid_stairs.append([z, i, j])
        self.grid_stairs = grid_stairs

    # find nearest stairs leading to the goal floor
    def find_nearest_stairs(self, position, goal_position):
        if not self.grid_stairs:
            self.find_all_stairs()
        x, y, z = position
        #print("z: " + str(z))
        xg, yx, zg = goal_position
        min_distance = float('inf')
        nearest_stairs = None
        for stair in self.grid_stairs:
            z2 = stair[0]
            #print("z2: " + str(z2))
            i = stair[1]
            j = stair[2]
            if z == z2 and self.grids[zg][i, j] == 'stair' and self.grids[z][i, j] == 'stair':
                distance = np.sqrt((x - i) ** 2 + (y - j) ** 2)
                if distance < min_distance:
                    min_distance = distance
                    nearest_stairs = (i, j, z)
        return nearest_stairs

    def heuristic(self, a, position_b):
        if not self.goals:
            return 0  # Return 0 if there are no goals

        # Calculate heuristic for each goal
        goal_heuristics = []
        for b in self.goals:
            dx = abs(b[0] - a[0])
            dy = abs(b[1] - a[1])
            dz = abs(b[2] - a[2])

            if self.minimize_cost:
                h = np.sqrt(dx ** 2 + dy ** 2) * self.grid_size
                if dz > 0:
                    nearest_stairs = self.find_nearest_stairs(a, b)
                    if nearest_stairs:
                        h += (np.sqrt((nearest_stairs[0] - a[0]) ** 2 + (nearest_stairs[1] - a[1]) ** 2) +
                              np.sqrt(
                                  (b[0] - nearest_stairs[0]) ** 2 + (b[1] - nearest_stairs[1]) ** 2)) * self.grid_size
                        h += dz * 3 * self.grid_size  # Increased floor change penalty
                    else:
                        h = float('inf')
                if self.buffered_grids[a[2]][a[0], a[1]] == 'walla':
                    h += 10 * self.grid_size  # Add a cost for wall-adjacent cells
            else:
                # For distance minimization, use 3D Euclidean distance
                h = np.sqrt(dx ** 2 + dy ** 2 + (dz * 3) ** 2) * self.grid_size
                if self.buffered_grids[a[2]][a[0], a[1]] == 'walla':
                    h += 10 * self.grid_size  # Add a cost for wall-adjacent cells even in distance mode

            goal_heuristics.append(h)

        if self.heuristic_style == 'sum':
            return sum(goal_heuristics)
        else:
            return min(goal_heuristics)

    def calculate_sparse_heuristic(self):
        if self.goals is None:
            return None

        floor_shape = self.grids[self.current_floor].shape
        x = np.linspace(0, floor_shape[0] - 1, self.heuristic_resolution)
        y = np.linspace(0, floor_shape[1] - 1, self.heuristic_resolution)
        xx, yy = np.meshgrid(x, y)

        heuristic_values = []
        for i in range(self.heuristic_resolution):
            for j in range(self.heuristic_resolution):
                x_coord = int(xx[i, j])
                y_coord = int(yy[i, j])
                if self.grids[self.current_floor][x_coord, y_coord] != 'wall':
                    h_value = self.heuristic((x_coord, y_coord, self.current_floor), self.goals)
                    heuristic_values.append((x_coord, y_coord, h_value))

        if not heuristic_values:
            return None

        x_sparse, y_sparse, z_sparse = zip(*heuristic_values)

        grid_x, grid_y = np.mgrid[0:floor_shape[0], 0:floor_shape[1]]
        heuristic_map = griddata((x_sparse, y_sparse), z_sparse, (grid_x, grid_y), method='cubic')

        # Set walls to NaN
        for i in range(floor_shape[0]):
            for j in range(floor_shape[1]):
                if self.grids[self.current_floor][i, j] == 'wall':
                    heuristic_map[i, j] = np.nan

        return heuristic_map

    def get_neighbors(self, current):
        x, y, z = current.position
        neighbors = []
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]
        if self.allow_diagonal:
            directions += [(1, 1), (1, -1), (-1, 1), (-1, -1)]

        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.buffered_grids[z].shape[0] and 0 <= ny < self.buffered_grids[z].shape[1]:
                if self.buffered_grids[z][nx, ny] not in ['wall', 'walla']:
                    neighbors.append(Node((nx, ny, z)))

        if self.buffered_grids[z][x, y] == 'stair':
            for nz in range(len(self.buffered_grids)):
                if nz != z and self.buffered_grids[nz][x, y] == 'stair':
                    neighbors.append(Node((x, y, nz)))

        return neighbors

    def get_cost(self, current, neighbor):
        dx = abs(neighbor.position[0] - current.position[0])
        dy = abs(neighbor.position[1] - current.position[1])
        dz = abs(neighbor.position[2] - current.position[2])

        if self.minimize_cost:
            cost = self.grid_size
            if self.buffered_grids[neighbor.position[2]][neighbor.position[0], neighbor.position[1]] == 'door':
                cost += 5 * self.grid_size
            elif self.buffered_grids[neighbor.position[2]][neighbor.position[0], neighbor.position[1]] == 'stair':
                cost += 1.25 * self.grid_size
            elif self.buffered_grids[neighbor.position[2]][neighbor.position[0], neighbor.position[1]] == 'walla':
                cost += 10 * self.grid_size  # Add a cost for wall-adjacent cells

            if self.allow_diagonal and dx + dy == 2:
                cost *= 1.414  # Diagonal movement cost
        else:
            # For distance minimization, use Euclidean distance
            cost = np.sqrt(dx ** 2 + dy ** 2) * self.grid_size
            if dz > 0:
                cost += 3 * self.grid_size  # Significant penalty for changing floors
            if self.buffered_grids[neighbor.position[2]][neighbor.position[0], neighbor.position[1]] == 'walla':
                cost += 10 * self.grid_size  # Add a cost for wall-adjacent cells even in distance mode

        return cost

    def run_algorithm(self, event):
        if not self.grid_stairs:
            self.find_all_stairs()
        if not self.start or not self.goals:
            print("Please set both start and at least one goal point.")
            return
        if self.algorithm == 'A*':
            self.run_astar()

    def run_astar(self):
        fps = self.fps
        time0 = time.time()
        self.path = None
        open_list = []
        closed_set = set()
        start_node = Node(self.start)
        start_node.h = self.heuristic(self.start, None)  # Calculate initial heuristic
        start_node.f = start_node.g + start_node.h

        heapq.heappush(open_list, (start_node.f, start_node))

        progress_counter = 0
        progress_threshold = 0  #max(1, int(100 / self.speed))

        while open_list:
            current_node = heapq.heappop(open_list)[1]

            if current_node.position in self.goals:
                self.visualize_progress(closed_set, [node for _, node in open_list], None)
                self.reconstruct_path(current_node)
                self.save_path_visualization()
                return

            closed_set.add(current_node.position)

            for neighbor in self.get_neighbors(current_node):
                if neighbor.position in closed_set:
                    continue

                tentative_g = current_node.g + self.get_cost(current_node, neighbor)

                if not any(node.position == neighbor.position for _, node in open_list):
                    neighbor.g = tentative_g
                    neighbor.h = self.heuristic(neighbor.position, None)
                    neighbor.f = neighbor.g + neighbor.h
                    neighbor.parent = current_node
                    heapq.heappush(open_list, (neighbor.f, neighbor))
                else:
                    for i, (f, node) in enumerate(open_list):
                        if node.position == neighbor.position and tentative_g < node.g:
                            node.g = tentative_g
                            node.f = node.g + node.h
                            node.parent = current_node
                            heapq.heapify(open_list)
                            break

            progress_counter += 1
            if progress_threshold == 0 or progress_counter >= progress_threshold:
                if time.time() - time0 > 1.0 / fps and self.animated:
                    time0 = time.time()
                    self.visualize_progress(closed_set, [node for _, node in open_list],
                                            self.get_current_path(current_node))
                    progress_counter = 0

        print("No path found to any goal.")

    def reconstruct_path(self, node):
        path = []
        path_length = 0
        while node:
            path.append(node.position)
            if node.parent:
                path_length += self.heuristic(node.position, node.parent.position)
            node = node.parent
        self.path = path[::-1]
        self.t_pathlength.set_val(f"{path_length:.2f}")
        self.pathlength = path_length
        self.visualize_path()

    def visualize_progress(self, closed_set, open_list, current_path):
        self.ax.clear()
        if self.wall_buffer > 0:
            colors = ['white', 'black', 'orange', 'red', 'lavenderblush', 'lightgray']
            color_map = ListedColormap(colors)
            grid = self.grid_to_numeric(self.buffered_grids[self.current_floor])
        else:
            colors = ['white', 'black', 'orange', 'red', 'lavenderblush']
            color_map = ListedColormap(colors)
            grid = self.grid_to_numeric(self.grids[self.current_floor])

        self.ax.imshow(grid.T, cmap=color_map, interpolation='nearest')

        # Plot closed set
        closed_on_floor = [node for node in closed_set if node[2] == self.current_floor]
        if closed_on_floor:
            closed_x, closed_y = zip(*[(node[0], node[1]) for node in closed_on_floor])
            self.ax.scatter(closed_x, closed_y, color='blue', alpha=0.1, s=20)

        # Plot open list
        open_on_floor = [node.position for node in open_list if node.position[2] == self.current_floor]
        if open_on_floor:
            open_x, open_y = zip(*[(node[0], node[1]) for node in open_on_floor])
            self.ax.scatter(open_x, open_y, color='aqua', alpha=0.4, s=20)

        # Plot current path
        if current_path:
            current_path_on_floor = [node for node in current_path if node[2] == self.current_floor]
            if len(current_path_on_floor) > 1:
                for i in range(len(current_path_on_floor) - 1):
                    start = current_path_on_floor[i]
                    end = current_path_on_floor[i + 1]

                    # Check if this segment is continuous or a jump
                    if abs(end[0] - start[0]) > 1 or abs(end[1] - start[1]) > 1:
                        # Discontinuous segment - draw in green
                        self.ax.plot([start[0], end[0]], [start[1], end[1]], color='green', linewidth=2, linestyle='--')
                    else:
                        # Continuous segment - draw in blue
                        self.ax.plot([start[0], end[0]], [start[1], end[1]], color='blue', linewidth=2)

        # Plot start and goal
        if self.start and self.start[2] == self.current_floor:
            self.ax.plot(self.start[0], self.start[1], 'go', markersize=10)
        for goal in self.goals:
            if goal and goal[2] == self.current_floor:
                self.ax.plot(goal[0], goal[1], 'ro', markersize=10)

        self.ax.set_title(f'Floor {self.current_floor + 1}')
        self.ax.axis('off')
        plt.draw()
        plt.pause(0.01)

    def visualize_path(self):
        self.ax.clear()

        if self.wall_buffer > 0:
            colors = ['white', 'black', 'orange', 'red', 'lavenderblush', 'lightgray']
            color_map = ListedColormap(colors)
            grid = self.grid_to_numeric(self.buffered_grids[self.current_floor])
        else:
            colors = ['white', 'black', 'orange', 'red', 'lavenderblush']
            color_map = ListedColormap(colors)
            grid = self.grid_to_numeric(self.grids[self.current_floor])

        self.ax.imshow(grid.T, cmap=color_map, interpolation='nearest')

        if self.path:
            path_on_floor = [node for node in self.path if node[2] == self.current_floor]
            for i in range(len(path_on_floor) - 1):
                start = path_on_floor[i]
                end = path_on_floor[i + 1]

                # Check if this segment is continuous or a jump
                if (abs(end[0] - start[0]) > 1 or abs(end[1] - start[1]) > 1):
                    # Discontinuous segment - draw in green
                    self.ax.plot([start[0], end[0]], [start[1], end[1]], color='green', linewidth=2, linestyle='--')
                else:
                    # Continuous segment - draw in blue
                    self.ax.plot([start[0], end[0]], [start[1], end[1]], color='blue', linewidth=2)

        if self.start and self.start[2] == self.current_floor:
            self.ax.plot(self.start[0], self.start[1], 'go', markersize=10)
        for goal in self.goals:
            if goal and goal[2] == self.current_floor:
                self.ax.plot(goal[0], goal[1], 'ro', markersize=10)

        self.ax.set_title(f'Floor {self.current_floor + 1}')
        self.ax.axis('off')
        plt.draw()
        plt.pause(0.001)

    import os
    import matplotlib.pyplot as plt

    def save_path_visualization(self):
        if not self.path:
            print("No path to visualize.")
            return

        # Determine which floors are part of the path
        floors_in_path = sorted(set(node[2] for node in self.path), reverse=True)

        # Create a new figure with subplots for each floor in the path
        fig, axes = plt.subplots(len(floors_in_path), 1, figsize=(12, 9 * len(floors_in_path)))
        if len(floors_in_path) == 1:
            axes = [axes]

        colors = ['white', 'black', 'orange', 'red', 'lavenderblush']
        color_map = ListedColormap(colors)

        for ax, floor_index in zip(axes, floors_in_path):
            grid = self.grid_to_numeric(self.grids[floor_index])
            ax.imshow(grid.T, cmap=color_map, interpolation='nearest')

            if self.start and self.start[2] == floor_index:
                ax.plot(self.start[0], self.start[1], 'go', markersize=10, label='Start')

            for i, goal in enumerate(self.goals):
                if goal[2] == floor_index:
                    ax.plot(goal[0], goal[1], 'ro', markersize=10)
                    ax.annotate(str(i + 1), (goal[0], goal[1]), color='white', ha='center', va='center')

            path_on_floor = [node for node in self.path if node[2] == floor_index]
            if path_on_floor:
                for i in range(len(path_on_floor) - 1):
                    start = path_on_floor[i]
                    end = path_on_floor[i + 1]

                    # Check if this segment is continuous or a jump
                    if (abs(end[0] - start[0]) > 1 or abs(end[1] - start[1]) > 1):
                        # Discontinuous segment - draw in green
                        ax.plot([start[0], end[0]], [start[1], end[1]], color='green', linewidth=2, linestyle='--')
                    else:
                        # Continuous segment - draw in blue
                        ax.plot([start[0], end[0]], [start[1], end[1]], color='blue', linewidth=2)

            ax.set_title(f'Floor {floor_index + 1}')
            ax.axis('off')

        plt.tight_layout()

        # Create subfolder with the same name as the JSON import (without extension)
        folder_name = os.path.splitext(os.path.basename(self.json_filename))[0]
        os.makedirs(folder_name, exist_ok=True)

        # Save the figure
        plt.savefig(os.path.join(folder_name, f"path_visualization_len_{str(int(self.pathlength))}.png"),
                    bbox_inches='tight', pad_inches=0.1)
        plt.close(fig)

        print(f"Path visualization saved in {folder_name}/path_visualization_len_{str(int(self.pathlength))}.png")

    def get_current_path(self, node):
        path = []
        while node:
            path.append(node.position)
            node = node.parent
        return path[::-1]


def main():
    fn = askopenfilename(filetypes=[("json files", "*.json")])
    pathfinder = InteractiveBIMPathfinder(fn)
    plt.show()


if __name__ == "__main__":
    main()
