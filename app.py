# -*- coding: utf-8 -*-

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st
import json
import streamlit.components.v1 as components
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter
from pyedhrec import EDHRec
import re
import requests_cache

# Setting up config for streamlit application
st.set_page_config(
    page_title="Magic the Gathering Analysis",
    page_icon="🎴",
    layout="wide",
    initial_sidebar_state='collapsed'
)

session = requests_cache.CachedSession('edh_cache', expire_after="18000")

edhrec = EDHRec()

font_css = """
<head>
<link href="//cdn.jsdelivr.net/npm/mana-font@latest/css/mana.min.css" rel="stylesheet" type="text/css" />
</head>
"""
st.markdown(font_css, unsafe_allow_html=True)

st.title("Magic the Gathering Analysis")

col1, col2, col3, col4 = st.columns(4, gap="medium")

# Import Scryfall data and create a dataframe with only the relevant columns
scryfall = pd.read_json("http://data.scryfall.io/oracle-cards/oracle-cards-20240505210241.json")
scryfall = scryfall[["name", "released_at", "mana_cost", "cmc", "type_line", "color_identity", "set_name", "rarity", "artist", "image_uris"]]

# Filter out irrelevant card types
noncard_types = ["Plane", "Token", "Emblem", "Attraction", "Dungeon", "Stickers", "Contraption"]
scryfall = scryfall[scryfall["type_line"].str.contains('|'.join(noncard_types)) == False]

# Fetch the data of Heerenveen community decks from the json file and create a dataframe called hveen
decks = pd.read_json("database_mtg.json")

hveen = pd.DataFrame.from_records(decks)

def parse_cardlist(card_list):
    parsed_cards = []
    for card in card_list:
        if re.match(r'\d+', card):
            count, name = card.split(maxsplit=1)
            parsed_cards.extend([name.strip()] * int(count))
        else:
            parsed_cards.append(card)
    return parsed_cards

hveen["cards"] = hveen["cards"].apply(parse_cardlist)

# Look up data on all cards in Heerenveen deck
def get_deckdata(cardslist):
    deck_data = scryfall[scryfall["name"].isin(cardslist)]
    deck_data = deck_data[["name", "released_at", "mana_cost", "cmc", "type_line", "color_identity", "set_name", "rarity", "artist", "image_uris"]]

    deck_data = deck_data[deck_data["type_line"].str.contains('|'.join(noncard_types)) == False]

    return deck_data

def create_manacurve(deck_data):
    manacurve_commander = pd.Series(deck_data.groupby(["cmc"])["name"].count()).to_dict()

    return manacurve_commander

commander_list = hveen["commander"].tolist()

def clean_card_names(card_list):
    pattern = re.compile(r'^\d+\s+')

    cleaned_list = [pattern.sub('', card) for card in card_list]
    cleaned_list = [card for card in cleaned_list]

    return cleaned_list

# Initialize dataframe for data of EDHRec
edh_df = pd.DataFrame(data=None, index=None, columns=["commander", "cards", "manacurve", "average_deck_noland"])
edh_cards = pd.DataFrame(data=None, index=None, columns=["name", "released_at", "mana_cost", "cmc", "type_line", "color_identity", "set_name", "rarity", "artist", "image_uris"])
edh_deckdata = pd.DataFrame(data=None, index=None, columns=["commander", "name", "released_at", "mana_cost", "cmc", "type_line", "color_identity", "set_name", "rarity", "artist", "image_uris"])
average_df = pd.DataFrame(data=None, index=None, columns=["commander", "name", "released_at", "mana_cost", "cmc", "type_line", "color_identity", "set_name", "rarity", "artist", "image_uris"])

# Function to request data for commanders in Heerenveen database from EDHRec
def get_edh(commander):
    commander_clean = commander.replace(" ", "-").replace("'","").replace(",","").lower()
    response = session.get("https://json.edhrec.com/pages/commanders/"+commander_clean+".json")
    return response.json()

for commander in commander_list:
    commander_data = get_edh(commander)
    name = str(commander)
    cardlist = commander_data["cardlist"]
    cardlist_df = pd.DataFrame(cardlist)
    cardnames = cardlist_df["name"].tolist()

    deckdata = get_deckdata(cardnames)

    average_deck = edhrec.get_commanders_average_deck(commander)
    average_deck = average_deck["decklist"]
    average_deck = clean_card_names(average_deck)
    average_deck = parse_cardlist(average_deck)
    average_deck_data = get_deckdata(average_deck)
    average_deck_data["commander"] = commander
    average_deck_noland = average_deck_data[~average_deck_data["type_line"].str.contains("Land", na=False, case=False)]
    
    manacurve = create_manacurve(average_deck_noland)
    
    # Write commander, card names, average decklist and manacurve to the EDHRec dataframe
    edh_df.loc[len(edh_df)] = [commander, cardnames, manacurve, average_deck_noland]
    
    for index, row in average_deck_noland.iterrows():
        average_df = pd.concat([average_df, average_deck_noland], ignore_index=True)
        
    average_df = average_df.drop_duplicates(subset=["commander", "name"])

    edh_deckdata = pd.concat([edh_deckdata, average_deck_data])

# Dataframe with all cards in Heerenveen decks
cards_hveen = hveen.explode("cards").set_index("player")
cards_hveen.rename(columns={"cards": "name"}, inplace=True)

hveen_deckdata = get_deckdata(cards_hveen["name"]).reset_index()
hveen_deckdata = pd.merge(cards_hveen, hveen_deckdata, on=["name"])
hveen_deckdata.drop(columns=["index"], inplace=True)

hveen_deckdata_nolands = hveen_deckdata[~hveen_deckdata["type_line"].str.contains("Land", case=False)]

by_commander = hveen_deckdata_nolands.groupby("commander")
manacurves = {}

for name, cmc in by_commander:
    mana_curve = cmc["cmc"].value_counts().to_dict()
    manacurves[name] = mana_curve

manacurves_df = pd.DataFrame(list(manacurves.items()), columns=['Commander', 'Mana Curve'])

flat_df = pd.DataFrame(manacurves)

mana_totals = {key: 0 for key in range(12 + 1)}
row_count = 0

for mana_dict in manacurves_df["Mana Curve"]:
     row_count += 1
     for key, value in mana_dict.items():
        mana_totals[key] += value

flat_data = []
for commander, mana_curve in manacurves.items():
    for mana_value, count in mana_curve.items():
        flat_data.append({"Commander": commander, "Mana value": mana_value, "Count": count})

long_manacurves = pd.DataFrame(flat_data)

average_mana_curve = {key: value / row_count for key, value in mana_totals.items()}

curve_x = list(average_mana_curve.keys())
curve_y = list(average_mana_curve.values())

# Card frequency analysis
card_frequency = hveen_deckdata["name"].value_counts().reset_index()
card_frequency = card_frequency.rename(columns={"count": "name", "name": "count"})

# Color identity analysis
color_identity_hveen = hveen_deckdata["color_identity"].loc[hveen_deckdata["name"].isin(["Land"]) == False].value_counts().reset_index()
color_identity_hveen.columns = ["color_identity", "count"]

color_identity_hveen = color_identity_hveen.sort_values(by="count", ascending=False)

mana_unicode = {
    'W': '\ue600',
    'U': '\ue601',
    'B': '\ue602',
    'R': '\ue603',
    'G': '\ue604',
    '': '\ue904'
}

def convert_to_unicode(char_list):
    return "".join(mana_unicode.get(char, "") for char in char_list)

color_identity_hveen["color_unicode"] = color_identity_hveen["color_identity"].apply(convert_to_unicode)
labels = color_identity_hveen["color_unicode"]
values = color_identity_hveen["count"]

common_props = dict(labels=labels, values=values)

color_discrete_map={
    '\ue600': "#fde7a2",  # White
    '\ue601': "#85b7e5",  # Blue
    '\ue602': "#7d76ab",  # Black
    '\ue603': "#d28282",  # Red
    '\ue604': "#a0c27c",  # Green
    '\ue904': "#808080",  # Grey
    '\ue600\ue601': "#add8e6",  # Light Blue
    '\ue600\ue602': "#d3d3d3",  # Light Grey
    '\ue600\ue603': "#ffcccc",  # Light Red
    '\ue600\ue604': "#90ee90",  # Light Green
    '\ue601\ue600': "#add8e6",  # Light Blue
    '\ue601\ue602': "#666699",  # Dark Blue
    '\ue601\ue603': "#800080",  # Purple
    '\ue601\ue604': "#4682b4",  # Steel Blue
    '\ue602\ue600': "#d3d3d3",  # Light Grey
    '\ue602\ue601': "#666699",  # Dark Blue
    '\ue602\ue603': "#808080",  # Grey
    '\ue602\ue604': "#006400",  # Dark Green
    '\ue603\ue600': "#ffcccc",  # Light Red
    '\ue603\ue601': "#800080",  # Purple
    '\ue603\ue602': "#808080",  # Grey
    '\ue603\ue604': "#b22222",  # Firebrick
    '\ue604\ue600': "#90ee90",  # Light Green
    '\ue604\ue601': "#4682b4",  # Steel Blue
    '\ue604\ue602': "#006400",  # Dark Green
    '\ue604\ue603': "#b22222",  # Firebrick
    '\ue600\ue601\ue602': "#778899",  # Light Slate Grey
    '\ue600\ue601\ue603': "#db7093",  # Pale Violet Red
    '\ue600\ue601\ue604': "#3cb371",  # Medium Sea Green
    '\ue600\ue602\ue603': "#bc8f8f",  # Rosy Brown
    '\ue600\ue602\ue604': "#32cd32",  # Lime Green
    '\ue600\ue603\ue604': "#ff4500",  # Orange Red
    '\ue601\ue602\ue600': "#778899",  # Light Slate Grey
    '\ue601\ue602\ue603': "#663399",  # Rebecca Purple
    '\ue601\ue602\ue604': "#8a2be2",  # Blue Violet
    '\ue601\ue603\ue600': "#db7093",  # Pale Violet Red
    '\ue601\ue603\ue602': "#663399",  # Rebecca Purple
    '\ue601\ue603\ue604': "#c71585",  # Medium Violet Red
    '\ue601\ue604\ue600': "#3cb371",  # Medium Sea Green
    '\ue601\ue604\ue602': "#8a2be2",  # Blue Violet
    '\ue601\ue604\ue603': "#c71585",  # Medium Violet Red
    '\ue602\ue600\ue601': "#778899",  # Light Slate Grey
    '\ue602\ue600\ue603': "#bc8f8f",  # Rosy Brown
    '\ue602\ue600\ue604': "#32cd32",  # Lime Green
    '\ue602\ue601\ue600': "#778899",  # Light Slate Grey
    '\ue602\ue601\ue603': "#663399",  # Rebecca Purple
    '\ue602\ue601\ue604': "#8a2be2",  # Blue Violet
    '\ue602\ue603\ue600': "#bc8f8f",  # Rosy Brown
    '\ue602\ue603\ue601': "#663399",  # Rebecca Purple
    '\ue602\ue603\ue604': "#a52a2a",  # Brown
    '\ue602\ue604\ue600': "#32cd32",  # Lime Green
    '\ue602\ue604\ue601': "#8a2be2",  # Blue Violet
    '\ue602\ue604\ue603': "#a52a2a",  # Brown
    '\ue603\ue600\ue601': "#db7093",  # Pale Violet Red
    '\ue603\ue600\ue602': "#bc8f8f",  # Rosy Brown
    '\ue603\ue600\ue604': "#ff4500",  # Orange Red
    '\ue603\ue601\ue600': "#db7093",  # Pale Violet Red
    '\ue603\ue601\ue602': "#663399",  # Rebecca Purple
    '\ue603\ue601\ue604': "#c71585",  # Medium Violet Red
    '\ue603\ue602\ue600': "#bc8f8f",  # Rosy Brown
    '\ue603\ue602\ue601': "#663399",  # Rebecca Purple
    '\ue603\ue602\ue604': "#a52a2a",  # Brown
    '\ue603\ue604\ue600': "#ff4500",  # Orange Red
    '\ue603\ue604\ue601': "#c71585",  # Medium Violet Red
    '\ue603\ue604\ue602': "#a52a2a",  # Brown
    '\ue604\ue600\ue601': "#3cb371",  # Medium Sea Green
    '\ue604\ue600\ue602': "#32cd32",  # Lime Green
    '\ue604\ue600\ue603': "#ff4500",  # Orange Red
    '\ue604\ue601\ue600': "#3cb371",  # Medium Sea Green
    '\ue604\ue601\ue602': "#8a2be2",  # Blue Violet
    '\ue604\ue601\ue603': "#c71585",  # Medium Violet Red
    '\ue604\ue602\ue600': "#32cd32",  # Lime Green
    '\ue604\ue602\ue601': "#8a2be2",  # Blue Violet
    '\ue604\ue602\ue603': "#a52a2a",  # Brown
    '\ue604\ue603\ue600': "#ff4500",  # Orange Red
    '\ue604\ue603\ue601': "#c71585",  # Medium Violet Red
    '\ue604\ue603\ue602': "#a52a2a"  # Brown
}

# Set default color for colorless cards and unknown combinations of colors
default_color = "#999999"

for label in labels: 
    if label not in color_discrete_map:
        color_discrete_map[label] = default_color

# Pie chart displaying color identity distribution in all cards used in Heerenveen decks
identity_chart = px.pie(color_identity_hveen, names=labels, values=values, hole=.3, color_discrete_sequence=[color_discrete_map[key] for key in labels], hover_name=labels, custom_data=["color_identity"])
# Setting fonts of chart labels and percentage correctly (for mana symbol font)
identity_chart.update_traces(
    textposition="inside", 
    textinfo="label+percent", 
    # insidetextfont=dict(color="white"),
    texttemplate="<span style='font-family:Mana'>%{label}</span><br><span style='font-family:Courier New'>%{percent}</span>",
    hovertemplate="<b style='font-family:Mana'>%{label}:</b> %{value} cards<extra></extra>"
)

identity_chart.update_layout(
  margin=dict(l=20, r=20, b=0, t=20),
  showlegend=False,
  font_size=18,
  title={
    "text":"",
    "xanchor": "left",
    "x":0    
  },
  font_family="Source Sans Pro"
)

# Artist analysis
land_types_pattern = '|'.join([re.escape(land_type) for land_type in "Land"])
artists_hveen = hveen_deckdata[~hveen_deckdata["type_line"].str.contains(land_types_pattern, na=False, case=False)]["artist"].value_counts().reset_index()
artists_hveen.columns = ["artist", "count"]
artists_hveen = artists_hveen.sort_values(by="count", ascending=False)

# Card type analysis
types = ["Artifact", "Instant", "Sorcery", "Creature", "Enchantment"]
all_types_global = average_df["type_line"].str.split("—| ")

def flatten_types(types_list):
  flattened_types = [word for sublist in types_list for word in sublist]
  flattened_types = [word for word in flattened_types if word in types]
  
  return flattened_types

def radar_chart(commander):
  commander_avg_deck = average_df[average_df["commander"] == commander]
  avg_commander_types = commander_avg_deck["type_line"].str.split("—| ")
  flattened_avg_commander_types = flatten_types(avg_commander_types)
  avg_commander_type_count = Counter(flattened_avg_commander_types)
  
  commander_types = hveen_deckdata[hveen_deckdata["commander"] == commander]["type_line"].str.split("—| ")
  flattened_commander_types = flatten_types(commander_types)

  avg_card_types = pd.DataFrame(avg_commander_type_count.items(), columns=["type", "type_count"]).sort_values("type", ascending=False)

  type_counts = Counter(flattened_commander_types)

  card_types = pd.DataFrame(type_counts.items(), columns=["type", "type_count"]).sort_values("type", ascending=False)
  card_types_chart = go.Figure()

  card_types_chart.add_trace(go.Scatterpolar(
      r=card_types["type_count"],
      theta=card_types["type"],
      fill="toself",
      fillcolor=px.colors.qualitative.Plotly[0],
      marker_color=px.colors.qualitative.Plotly[0],
      opacity=0.8,
      name=commander
  ))

  card_types_chart.add_trace(go.Scatterpolar(
      r=avg_card_types["type_count"],
      theta=avg_card_types["type"],
      line=dict(         
          dash="dot"
      ),
      marker_color=px.colors.qualitative.Plotly[1],
      opacity=0.8,
      name="Average deck"
  ))

  card_types_chart.update_layout(
      polar=dict(
          radialaxis=dict(
              visible=True
          )
      ),
      showlegend=True,
      title="",
      margin_t=10,
      margin_l=50,
      margin_b=0,
      height=400
      )

  return card_types_chart

# Land vs mana rock analysis
land_cards = hveen_deckdata[hveen_deckdata["type_line"].str.contains("Land", case=False, na=False)]
mana_rocks = ["Abzan Banner", "Alloy Myr", "Arcane Signet", "Arcum's Astrolabe", "Astral Cornucopia", "Atarka Monument", "Azorius Cluestone", "Azorius Keyrune", "Azorius Locket", "Azorius Signet", "Basalt Monolith", "Black Mana Battery", "Bloodstone Cameo", "Blue Mana Battery", "Boros Cluestone", "Boros Keyrune", "Boros Locket", "Boros Signet", "Caged Sun", "Celestial Prism", "Charcoal Diamond", "Chromatic Lantern", "Chrome Mox", "Coalition Relic", "Coldsteel Heart", "Copper Myr", "Cryptolith Fragment", "Cultivator's Caravan", "Darksteel Ingot", "Dimir Cluestone", "Dimir Keyrune", "Dimir Locket", "Dimir Signet", "Doubling Cube", "Drake-Skull Cameo", "Dreamstone Hedron", "Dromoka Monument", "Everflowing Chalice", "Eye of Ramos", "Fellwar Stone", "Fieldmist Borderpost", "Fire Diamond", "Firewild Borderpost", "Fountain of Ichor", "Gemstone Array", "Gilded Lotus", "Gold Myr", "Golgari Cluestone", "Golgari Keyrune", "Golgari Locket", "Golgari Signet", "Green Mana Battery", "Grim Monolith", "Gruul Cluestone", "Gruul Keyrune", "Gruul Locket", "Gruul Signet", "Heart of Ramos", "Hedron Archive", "Hierophant's Chalice", "Honor-Worn Shaku", "Horn of Ramos", "Iron Myr", "Izzet Cluestone", "Izzet Keyrune", "Izzet Locket", "Izzet Signet", "Jeskai Banner", "Kolaghan Monument", "Leaden Myr", "Lion's Eye Diamond", "Lotus Bloom", "Lotus Petal", "Mana Crypt", "Mana Cylix", "Mana Geode", "Mana Prism", "Mana Vault", "Manalith", "Marble Diamond", "Mardu Banner", "Mind Stone", "Mistvein Borderpost", "Moss Diamond", "Mox Amber", "Mox Diamond", "Mox Emerald", "Mox Jet", "Mox Opal", "Mox Pearl", "Mox Ruby", "Mox Sapphire", "Mox Tantalite", "Myr Reservoir", "Obelisk of Bant", "Obelisk of Esper", "Obelisk of Grixis", "Obelisk of Jund", "Obelisk of Naya", "Ojutai Monument", "Opaline Unicorn", "Orzhov Cluestone", "Orzhov Keyrune", "Orzhov Locket", "Orzhov Signet", "Palladium Myr", "Pentad Prism", "Phyrexian Lens", "Pillar of Origins", "Powerstone Shard", "Prismatic Geoscope", "Prismatic Lens", "Pristine Talisman", "Prophetic Prism", "Rakdos Cluestone", "Rakdos Keyrune", "Rakdos Locket", "Rakdos Signet", "Red Mana Battery", "Seashell Cameo", "Selesnya Cluestone", "Selesnya Keyrune", "Selesnya Locket", "Selesnya Signet", "Serum Powder", "Silumgar Monument", "Silver Myr", "Simic Cluestone", "Simic Keyrune", "Simic Locket", "Simic Signet", "Sisay's Ring", "Skull of Ramos", "Sky Diamond", "Sol Grail", "Sol Ring", "Spectral Searchlight", "Spinning Wheel", "Springleaf Drum", "Star Compass", "Sultai Banner", "Talisman of Conviction", "Talisman of Creativity", "Talisman of Curiosity", "Talisman of Dominance", "Talisman of Hierarchy", "Talisman of Impulse", "Talisman of Indulgence", "Talisman of Resilience", "Temur Banner", "Thought Vessel", "Thran Dynamo", "Tigereye Cameo", "Tooth of Ramos", "Troll-Horn Cameo", "Unstable Obelisk", "Ur-Golem's Eye", "Veinfire Borderpost", "Vessel of Endless Rest", "White Mana Battery", "Wildfield Borderpost", "Worn Powerstone"]

mana_rocks_cards = hveen_deckdata[hveen_deckdata["name"].isin(mana_rocks)]

land_count = land_cards.groupby("commander").size()
mana_rocks_count = mana_rocks_cards.groupby("commander").size()

rock_ratio = pd.DataFrame({
    "Commander": commander,
    "Land Count": land_count,
    "Mana Rock Count": mana_rocks_count
})

rock_ratio = rock_ratio.fillna(0)

rock_ratio.reset_index(inplace=True)
rock_ratio["Ratio"] = rock_ratio["Land Count"] / rock_ratio["Mana Rock Count"]

rock_ratio.replace([np.inf, -np.inf], np.nan, inplace=True)
rock_ratio.fillna(0, inplace=True)

rock_ratio_chart = px.bar(rock_ratio, x="commander", y=["Land Count", "Mana Rock Count"], title=None, color_discrete_sequence=px.colors.qualitative.Plotly).update_layout(
    xaxis_title="Deck", yaxis_title="Number of cards", showlegend=False
)
rock_ratio_chart["data"][0].hovertemplate = "Land Count: %{y}<extra></extra>"
rock_ratio_chart["data"][1].hovertemplate = "Mana Rock Count: %{y}<extra></extra>"

# Analysis of ratity per deck
rarities_df = hveen_deckdata.groupby(["commander", "rarity"]).size().reset_index(name="counts")

rarity_plot = px.scatter(rarities_df, x='rarity', y='counts', 
                         color='commander',
                         title=None, height=600)

rarity_plot.update_layout(
    xaxis=dict(
        tickmode="array",
        tickvals=[0,1,2,3,4],
        ticktext=["common", "uncommon", "rare", "mythic", "special"]
    ),
    showlegend=False
)

rarity_plot.update_traces(
    marker=dict(size=10)
)

with col1:
    st.write("<h2 style='font-size:20px'>Our local MTG EDH meta</h3><p>Using decklists from 10 EDH players from my local MTG community, I wanted to explore our local meta. A meta can be broken up into many aspects. For this dashboard I focused on <span style='color:#636EFA'>color identity, land/mana rock ratio, rarity, card types and high synergy cards.</span><br/>So, are we creative deck builders, or do we simply follow global trends? Judge for yourself! :)</p>", unsafe_allow_html=True)
    st.divider()
    st.write("<h2 style='font-size:20px'>Color identities of cards across all decks</h3>", unsafe_allow_html=True)
    st.plotly_chart(identity_chart, theme=None, use_container_width=True)
    st.divider()

with col2:
    st.write("<h2 style='font-size:20px'>Ratio of Lands to Mana Rocks for our local decks</h2>", unsafe_allow_html=True)
    st.plotly_chart(rock_ratio_chart, use_container_width=True)
    st.divider()

    st.write("<h2 style='font-size:20px'>How rare are the cards in our decks?</h2>", unsafe_allow_html=True)
    st.plotly_chart(rarity_plot, use_container_width=True)

with col3:
    choose_commander = st.selectbox("Select your commander:", commander_list)
    st.write("<h2 style='font-size:20px'>Card types for ", choose_commander, "</h2>", unsafe_allow_html=True)
    card_types_chart = radar_chart(choose_commander)
    st.plotly_chart(card_types_chart, use_container_width=True)
    st.divider()

    st.write("<h2 style='font-size:20px'>Starting hand for your commander</h2>", unsafe_allow_html=True)
    commander_deck = hveen_deckdata.loc[hveen_deckdata["commander"] == choose_commander]
    random_hand = commander_deck.sample(n=7)
    random_hand = random_hand["name"].tolist()
    image_uris_list = []
    for card_name in random_hand:
        card_row = scryfall[scryfall['name'] == card_name]
        normal_uri = card_row.iloc[0]['image_uris'].get('normal') if 'normal' in card_row.iloc[0]['image_uris'] else None
    
        if normal_uri:
            image_uris_list.append(normal_uri)
    
    st.image(image_uris_list, width=130)
    

with col4:
    st.write("<h2 style='font-size:20px'>Mana curve of ", choose_commander," vs. average manacurve</h2>", unsafe_allow_html=True)
    manacurve_graph = px.histogram(long_manacurves[long_manacurves["Commander"] == choose_commander], x="Mana value", y="Count", color="Commander", color_discrete_sequence=px.colors.qualitative.Plotly).update_layout(
        showlegend=False,
        xaxis=dict(
            tickmode = "array",
            tickvals = [i + 0.5 for i in range(0, 12)],
            ticktext = [str(i) for i in range(0, 12)],
            dtick = 1
        ),
        bargap=0.1
    )
    manacurve_graph.update_traces(
        xbins=dict(
            start=0,
            end=12,
            size=1
        )
    )

    curve_x_centered = [x + 0.5 for x in curve_x]
                     
    manacurve_graph.add_trace(go.Scatter(x=curve_x_centered, y=curve_y, mode="lines", name="Average Mana Curve", line=dict(color="cornsilk")))
    st.plotly_chart(manacurve_graph, use_container_width=True)
    st.divider()

    high_synergy_cards = edhrec.get_high_synergy_cards(choose_commander)
    high_synergy_cards_list = [card["name"] for card in high_synergy_cards["High Synergy Cards"]]

    commander_df = average_df[average_df["commander"] == choose_commander].reset_index(drop=True)

    card_names_set = set(commander_df["name"])

    cards_not_in_df = [card for card in high_synergy_cards_list if card not in card_names_set]

    st.write("<h2 style='font-size:20px'>High Synergy Suggestions</h2>", unsafe_allow_html=True)
    if not cards_not_in_df:
        st.write("Your deck already has all the high synergy cards recommended for ", choose_commander)
    else:
        st.write("Your deck might benefit from these high synergy cards:<br/>", ", ".join(cards_not_in_df), unsafe_allow_html=True)
    
user_decklist_dict = {
        "player": "",
        "commander": "",
        "cards": ""
    }

def append_deck_to_json(file_path, new_deck):
    if new_deck["player"] and new_deck["commander"] and new_deck["cards"]:
        try:
            with open(file_path, "r") as file:
                data = json.load(file)
            
            data.append(new_deck)

            with open(file_path, "w") as file:
                json.dump(data, file, indent=4)
        except json.JSONDecodeError as e:
            st.write(f"An error occured: {e}")
    
    else:
        st.write("The text input fields are empty, please add a commander and decklist first")

st.session_state["data_appended"] = False

with st.sidebar:
    user_decklist = st.text_area(label="Add your own decklist", value="")
    user_commander = st.text_input(label="Your commander:", value="")
    user_ID = 7

    user_decklist = list(user_decklist.replace('1 ', '').replace('\n', ',').split(','))
    user_decklist_dict["player"] = user_ID
    user_decklist_dict["commander"] = user_commander
    user_decklist_dict["cards"] = user_decklist
    json_file_path = "database_mtg.json"

    if st.button("Submit Decklist"):
        if not st.session_state["data_appended"]:
            append_deck_to_json(json_file_path, user_decklist_dict)
            st.session_state["data_appended"] = True
            st.write("Decklist succesfully added!")
        else:
            st.write("Decklist has already been added.")
