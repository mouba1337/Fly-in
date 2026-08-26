*This project has been created as part of the 42 curriculum by mhend.*

---

## Description

**Fly-In** is an advanced drone routing simulation designed to navigate multiple drones through complex, restricted airspace without collisions. The core goal of this project is to parse a defined map of interconnected zones and calculate the most efficient flight schedules for a fleet of drones moving from a starting hub to their final destinations.

The simulation ensures strict adherence to dynamic capacity constraints—meaning neither the landing zones nor the mid-air connections can exceed their maximum allowable drone traffic at any given second.

---

## Instructions

### Prerequisites

Ensure you have **Python 3.10+** installed, along with `uv` for fast dependency management and environment creation.

### Installation

1. Clone the repository and navigate into the project folder:
```bash
git clone <repository_url>
cd fly-in

```


2. Install the necessary dependencies (including the `rich` library for the UI):
```bash
uv sync

```



### Execution

You can run the simulation using the provided `Makefile` or directly via the command line.

The map file is passed with the `--map` option.

**Using the Makefile:**

```bash
make run MAP=maps/easy/01_linear_path.txt
```

**Or directly:**

```bash
uv run python main.py --map maps/challenger/01_the_impossible_dream.txt
```

### Example

Input — `maps/easy/01_linear_path.txt`:

```
# Easy Level 1: Simple linear path
nb_drones: 2

start_hub: start 0 0 [color=green]
hub: waypoint1 1 0 [color=blue]
hub: waypoint2 2 0 [color=blue]
end_hub: goal 3 0 [color=red]

connection: start-waypoint1
connection: waypoint1-waypoint2
connection: waypoint2-goal
```

Output — one line per simulation turn, drones that do not move are omitted:

```
D1-waypoint1
D1-waypoint2 D2-waypoint1
D1-goal D2-waypoint2
D2-goal
```

Both drones are delivered in 4 turns. `waypoint1` and `waypoint2` have the
default capacity of 1, so `D2` follows one turn behind `D1` rather than
sharing a zone with it.

---

## Algorithm Choices and Implementation Strategy

The project architecture heavily leverages **Object-Oriented Programming (OOP)** to separate data parsing, simulation logic, and UI rendering into distinct, flexible modules.

* **Space-Time Graph:** Standard graphs only represent physical space. To avoid mid-air collisions, the graph structure was engineered to incorporate a *time* dimension. Every connection and zone maintains a `Timeline` (a list of integers) that acts as a reservation ledger, tracking exactly how many drones are occupying that space at any specific turn.
* **Breadth-First Search (BFS):** Because the drones need to find the shortest possible path while navigating dynamic bottlenecks, a customized BFS algorithm is used. BFS explores the graph layer by layer, but instead of just checking if a neighboring node is physically connected, it queries the `Timeline` to verify if the connection and destination have available capacity during the upcoming turn.
* **Generator Pipeline:** The simulation utilizes Python generators (`yield` and `yield from`) to stream drone movements turn-by-turn. This prevents the program from calculating and storing massive lists of moves in memory all at once, allowing it to efficiently handle large-scale maps.

---

## Visual Representation Features

The terminal interface was built using the `rich` library to elevate the user experience from a standard text dump into an easy-to-read, dynamic dashboard.

* **Color-Coded Drones:** Each drone is assigned a stable color from a dynamically applied palette. As drones move across the map, their IDs and destinations are printed in their designated color, making it effortless for the user to track individual paths through chaotic junctions.
* **Dynamic Text Wrapping:** Utilizing `soft_wrap=True` and `crop=False`, the UI ensures that complex turns with massive amounts of drone traffic seamlessly wrap to the next line without ever truncating data or breaking the layout.

---

## Resources

* **Peer Learning:** Extensive collaboration and discussions with fellow 1337 students to brainstorm space-time graph logic and refine OOP architecture.
* **GeeksforGeeks:** Used as a reference for mastering foundational graph data structures, Python object iteration mechanics, and standard Breadth-First Search traversal logic.
* **YouTube:** Consulted various tutorials to deepen understanding of advanced Python OOP principles (like `__future__` annotations, class decorators, and generator delegation with `yield from`).
* **AI Assistance:** AI was utilized strictly as an interactive debugging and formatting tool. It was used to analyze and demystify complex Python tracebacks (such as identifying the root cause of `'int' object is not iterable` and `'dict' object is not callable` errors during generator looping), to optimize string formatting and terminal wrapping inside the `rich` UI classes, and to brainstorm the logic for extracting turn-by-turn data into the capacity dashboard.