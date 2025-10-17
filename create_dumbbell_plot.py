import matplotlib.pyplot as plt

# Data with team information - Division 3, Group A
# Format: (player, team, nl, ggl)
player_data = [
    # BetaFrost Blue
    ('Kulsol', 'BetaFrost Blue', 1, 1.53),
    ('Odinof', 'BetaFrost Blue', 1, 1.53),
    ('Shakkalakka', 'BetaFrost Blue', 0.17, 0.96),

    # Buskelusk
    ('Buggibear', 'Buskelusk', 0.5, 1.3),
    ('Lundez', 'Buskelusk', 0, 0),  # Not in original image
    ('RougeShrimp', 'Buskelusk', 1, 0.72),
    ('toAZty_TV', 'Buskelusk', 0.33, 0.51),

    # FJORDEN
    ('Calmface', 'FJORDEN', 3.17, 1.94),
    ('LastLivingInka', 'FJORDEN', 1, 0.86),
    ('Ulveeen', 'FJORDEN', 4.83, 2.5),

    # Foxed Gaming
    ('Arefisk', 'Foxed Gaming', 0.67, 0.3),
    ('Psywerx', 'Foxed Gaming', 0.5, 0.38),
    ('TEBAKK', 'Foxed Gaming', 1.5, 0.97),

    # Grumpy Old Bitches
    ('BobMalin', 'Grumpy Old Bitches', 3.17, 0.91),
    ('Fluffy4You', 'Grumpy Old Bitches', 1.17, 0.8),

    # hack0rz
    ('naicuu', 'hack0rz', 1, 1.5),
    ('Nullan', 'hack0rz', 1.5, 1.77),

    # Rafsepatruljen
    ('Lars_O', 'Rafsepatruljen', 0.33, 0.2),
    ('Rovii', 'Rafsepatruljen', 0.17, 0),
    ('Runningdwarf', 'Rafsepatruljen', 0, 0.56),

    # Team Midlife Crisis
    ('KimBrink', 'Team Midlife Crisis', 1.5, 0.88),
    ('madm1ral', 'Team Midlife Crisis', 1.8, 1.12),
    ('Nygaard316', 'Team Midlife Crisis', 0.33, 0.58),

    # The penetrators
    ('KokkoS', 'The penetrators', 1.17, 0.75),
    ('Kveitemjol', 'The penetrators', 1.83, 1.77),

    # Valhall Einherjar
    ('Tobben_03-123', 'Valhall Einherjar', 1, 1.4),

    # Valhall Valkyrie
    ('Angel-Ranger', 'Valhall Valkyrie', 1.33, 0.95),
    ('Bohaba', 'Valhall Valkyrie', 0.33, 0.67),
    ('Stinesh', 'Valhall Valkyrie', 1.67, 0.37),

    # What The Cluck
    ('Slohoinn', 'What The Cluck', 1, 0.82),
]

# Sort by team name first, then by player name
player_data.sort(key=lambda x: (x[1], x[0]))

# Unpack sorted data
sorted_players = [d[0] for d in player_data]
sorted_teams = [d[1] for d in player_data]
sorted_nl = [d[2] for d in player_data]
sorted_ggl = [d[3] for d in player_data]

# Create the plot
fig, ax = plt.subplots(figsize=(12, 16))

# Track team changes for horizontal lines
current_team = None
team_boundaries = []

# Plot the dumbbells
for i in range(len(sorted_players)):
    y_pos = i

    # Track team boundaries
    if sorted_teams[i] != current_team:
        if current_team is not None:
            team_boundaries.append(i - 0.5)
        current_team = sorted_teams[i]

    # Draw the line connecting the two points
    ax.plot([sorted_nl[i], sorted_ggl[i]], [y_pos, y_pos],
            color='gray', linewidth=1.5, zorder=1, alpha=0.7)

    # Draw the dots
    ax.scatter(sorted_nl[i], y_pos, color='#2E86AB', s=100, zorder=2, label='NL' if i == 0 else '')
    ax.scatter(sorted_ggl[i], y_pos, color='#A23B72', s=100, zorder=2, label='GGL' if i == 0 else '')

# Add horizontal lines to separate teams
for boundary in team_boundaries:
    ax.axhline(y=boundary, color='lightgray', linestyle='--', linewidth=1, alpha=0.5, zorder=0)

# Create y-axis labels with team names
y_labels = []
for i in range(len(sorted_players)):
    if i == 0 or sorted_teams[i] != sorted_teams[i-1]:
        # First player in a team - show team name
        y_labels.append(f"{sorted_players[i]} [{sorted_teams[i]}]")
    else:
        # Other players - just show name
        y_labels.append(sorted_players[i])

# Customize the plot
ax.set_yticks(range(len(sorted_players)))
ax.set_yticklabels(y_labels, fontsize=9)
ax.set_xlabel('Average Kills', fontsize=12, fontweight='bold')
ax.set_title('Player Performance Comparison: NL vs GGL\nDivision 3, Group A (Grouped by Team)',
             fontsize=14, fontweight='bold', pad=20)
ax.grid(axis='x', alpha=0.3, linestyle='--')
ax.set_axisbelow(True)

# Add legend
handles, labels = ax.get_legend_handles_labels()
ax.legend(handles[:2], labels[:2], loc='lower right', fontsize=10)

# Adjust layout
plt.tight_layout()

# Save the plot
plt.savefig('dumbbell_plot_nl_vs_ggl.png', dpi=300, bbox_inches='tight')
print("Dumbbell plot saved as 'dumbbell_plot_nl_vs_ggl.png'")
print(f"Total players: {len(sorted_players)}")
print(f"Total teams: {len(set(sorted_teams))}")

# Show the plot
plt.show()
