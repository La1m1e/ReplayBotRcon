import discord
from discord import Option
import os
import dotenv
import re
import json
from mcipc.rcon.je import Client as RCONClient
dotenv.load_dotenv()

RCON_HOST = os.getenv("RCON_HOST")
RCON_PORT = int(os.getenv("RCON_PORT"))
RCON_PASSWORD = os.getenv("RCON_PASSWORD")
VIEWS_FILE = "views.json"
bot = discord.Bot()


def store_view_data(data, path=VIEWS_FILE):
    try:
        with open(path, "r") as f:
            views = json.load(f)
    except FileNotFoundError:
        views = []
    views.append(data)
    with open(path, "w") as f:
        json.dump(views, f)

def remove_view_data(message_id, path=VIEWS_FILE):
    try:
        with open(path, "r") as f:
            views = json.load(f)
    except FileNotFoundError:
        views = []
    views = [v for v in views if v["message_id"] != message_id]
    with open(path, "w") as f:
        json.dump(views, f)


async def send_rcon_command(command: str) -> str:
    try:
        with RCONClient(RCON_HOST, RCON_PORT) as client:
            client.login(RCON_PASSWORD)
            response = client.run(command)
            return response
    except Exception as e:
        return f"RCON Error: {e}"


class StopReplay(discord.ui.View):
    def __init__(self, name: str, filename: str = None):
        super().__init__(timeout=None)
        self.name = name
        self.filename = filename
        if self.filename:
            self.add_item(self.DownloadReplayButton(self.name, self.filename))

    @discord.ui.button(label="STOP REPLAY", style=discord.ButtonStyle.danger, custom_id="stop_replay_button")
    async def stop_replay(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.clear_items()

        rcon_command = f"/replay stop chunks named {self.name}"
        rcon_response = await send_rcon_command(rcon_command)

        try:
            self.filename = rcon_response.split(":")[1].strip()
        except IndexError:
            self.filename = "unknown"

        self.add_item(self.DownloadReplayButton(self.name, self.filename))

        embed = discord.Embed(title=self.name, color=discord.Color.red())
        embed.add_field(name="Name", value=self.name)
        embed.add_field(name="FileName", value=self.filename)
        embed.set_footer(text="Replay has been stopped.")

        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.defer()

        # Update the persistent storage
        remove_view_data(interaction.message.id)
        store_view_data({
            "message_id": interaction.message.id,
            "channel_id": interaction.channel.id,
            "name": self.name,
            "filename": self.filename
        })

    class DownloadReplayButton(discord.ui.Button):
        def __init__(self, name: str, filename: str):
            super().__init__(label="Download replay", style=discord.ButtonStyle.primary, custom_id=f"download_{name}")
            self.name = name
            self.filename = filename

        async def callback(self, interaction: discord.Interaction):
            command = f'/replay download chunks "{self.name}" "{self.filename.split(".")[0]}"'
            response = await send_rcon_command(command)
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Download Replay",
                    description=f"[Click here to download your replay]({response.split(']:')[-1]})",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )

class Modal(discord.ui.Modal):
    def __init__(self, dimension: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dimension = dimension

        self.add_item(discord.ui.InputText(label="Starting chunk coordinates"))
        self.add_item(discord.ui.InputText(label="End chunk coordinates"))
        self.add_item(discord.ui.InputText(label="Name"))

    async def callback(self, interaction: discord.Interaction):
        start_coords = self.children[0].value.strip()
        end_coords = self.children[1].value.strip()
        name = self.children[2].value.strip()
        coord_pattern = r"^-?\d+\s-?\d+$"
        if not re.match(coord_pattern, start_coords) or not re.match(coord_pattern, end_coords):
            await interaction.response.send_message(
                "Please input chunk coordinates in the format: `chunkX chunkY` (e.g., `10 12`)",
                ephemeral=True
            )
            return
        name_pattern = r"^[\w\-]{1,20}$"
        if not re.match(name_pattern, name):
            await interaction.response.send_message(
                "Name must be 1–20 characters, only letters, numbers, underscores, or hyphens. No spaces or special characters allowed.",
                ephemeral=True
            )
            return
        embed = discord.Embed(title="Replay " + name, color=discord.Color.blue())
        embed.add_field(name="Starting chunk coordinates", value=self.children[0].value)
        embed.add_field(name="End chunk coordinates", value=self.children[1].value)
        embed.add_field(name="Name", value=name)
        embed.add_field(name="Dimension", value=self.dimension)
        await interaction.response.defer()
        rcon_command = f"/replay start chunks from {self.children[0].value} to {self.children[1].value} in minecraft:{self.dimension} named {name}"
        rcon_response = await send_rcon_command(rcon_command)
        print(rcon_response)
        view = StopReplay(name=name)
        msg = await interaction.followup.send(embeds=[embed], view=view)
        store_view_data({
            "message_id": msg.id,
            "channel_id": msg.channel.id,
            "name": name
        })


@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")
    try:
        with open(VIEWS_FILE) as f:
            views = json.load(f)
    except FileNotFoundError:
        views = []

    for v in views:
        try:
            channel = bot.get_channel(v["channel_id"])
            if channel is None:
                continue
            await channel.fetch_message(v["message_id"])  # Optional: to ensure it still exists
            view = StopReplay(name=v["name"], filename=v.get("filename"))
            bot.add_view(view, message_id=v["message_id"])
        except Exception as e:
            print(f"Error restoring view for message {v['message_id']}: {e}")

@bot.slash_command(
    guild_ids=[os.getenv("GUILD_ID")],
    dm_permission = False
)
async def replay(
    ctx,
    dimension: Option(str, "Select the dimension", choices=["overworld", "the_nether", "the_end"])
):
    modal = Modal(title="ReplayStart", dimension=dimension)
    await ctx.send_modal(modal)


bot.run(os.getenv("discordToken"))
