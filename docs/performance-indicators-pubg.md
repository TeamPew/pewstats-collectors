# Metrics

These are metrics that I want to track as part of an overall system for tracking, analysing and measuring performance and performance development on both individual and team levels. 

## Finishing 

Description: The ability to finish fights, by converting knocks (dbno) and damage to actual kills. 
Why is this important: A knock feels good, but if the enemy can revive, it does not necessarily mean that much in the greater scheme of things. Finishing shows to what agree the team can secure eliminations, resulting in points. 
How to measure: Telemtry data contains two events, LogPlayerMakeGroggy and LogPlayerKillV2. (LogPlayerKill for tournaments). These contain data about the knocks, and if the knock was converted to a kill. 

For each match, I want to know the number of knocks for each player, and then how many of those were converted into kills. I want to track additonal data such as: 

- map name
- game mode
- game type
- team id 
- date 
- time
- rank (team placement in the match)

