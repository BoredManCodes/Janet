###
# Taken entirely from Dis-Secretary, project has no license as per usual. Polls, do the license thing one day pls
# https://github.com/Discord-Snake-Pit/Dis-Secretary/blob/master/scales/githubMessages.py
# Removed PR stuff for now
###

import asyncio
import re
import textwrap
import traceback
from pathlib import Path
from lxml import html
import aiohttp
import bs4
import github.GithubException
import requests
from dis_snek import (
    Scale,
    Message,
    Embed,
    MaterialColors,
    listen,
    ButtonStyles,
    Button,
    component_callback,
    ComponentContext,
)
from github import Github

snippet_regex = re.compile(
    r"github\.com/([\w\-_]+)/([\w\-_]+)/blob/([\w\-_]+)/([\w\-_/.]+)(#L[\d]+(-L[\d]+)?)?"
)
commit_regex = re.compile(r"github\.com(?:/[^/]+)*/commit/[0-9a-f]{40}"
)

class GithubMessages(Scale):
    def __init__(self, bot):
        self.git = Github(
            (Path(__file__).parent.parent / "git_token.txt").read_text().strip()
        )
        self.repo = self.git.get_repo("BoredManCodes/Janet")

    @component_callback("delete")
    async def delete_resp(self, context: ComponentContext):
        await context.defer(ephemeral=True)
        reply = await self.bot.cache.fetch_message(
            context.message.message_reference.channel_id,
            context.message.message_reference.message_id,
        )
        if reply:
            if context.author.id == reply.author.id:
                await context.send("Okay!", ephemeral=True)
                await context.message.delete()
            else:
                await context.send(
                    "You do not have permission to delete that!", ephemeral=True
                )
        else:
            await context.send("An unknown error occurred", ephemeral=True)

    async def reply(self, message: Message, **kwargs):
        await message.suppress_embeds()
        await message.reply(
            **kwargs,
            components=[Button(ButtonStyles.RED, emoji="🗑️", custom_id="delete")],
        )

    async def get_commit(self, message: Message):
        results = commit_regex.findall(message.content)[0]
        results = "github.com/Discord-Snake-Pit/Dis-Snek/commit/f5b815a5d9b98d8d71edfe8091537903fa9f762a"
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://{results}") as resp:
                if resp.status != 200:
                    return

                # file_data = await resp.text()
                # source = bs4.BeautifulSoup(file_data, "html.parser")
                tree = html.fromstring(resp.text)
                commit_data = tree.xpath('/html/body/div[5]/div/main/div[2]/div/div[4]/div[3]/div/div[2]/div/table')
                commit_info = tree.xpath('/html/body/div[5]/div/main/div[2]/div/div[2]/div[4]/div[2]')
                print(commit_info)
                print(commit_data)



                # page = source.("tbody")
                # print(source)
                #
                #
                # embed = Embed(
                #     title=f"{user}/{repo}",
                #     description=f"```{extension}\n{textwrap.dedent(file_data)}```",
                # )
                #
                # await self.reply(message, embeds=embed)



    async def get_pull(self, repo, pr_id: int):
        try:
            pr = await asyncio.to_thread(repo.get_pull, pr_id)
            return pr

        except github.UnknownObjectException:
            return None

    async def get_issue(self, repo, issue_id: int):
        try:
            issue = await asyncio.to_thread(repo.get_issue, issue_id)
            return issue

        except github.UnknownObjectException:
            return None

    def assemble_body(self, body: str, max_lines=10):
        """Cuts the body of an issue / pr to fit nicely"""
        output = []
        body = (body or "No Description Given").split("\n")

        start = 0
        for i in range(len(body)):
            if body[i].startswith("## Description"):
                start = i + 1

            if body[i].startswith("## Checklist"):
                body = body[:i]
                break
        code_block = False

        for i in range(len(body)):
            if i < start:
                continue

            line = body[i].strip("\r")
            if line in ["", "\n", " "] or line.startswith("!image"):
                continue
            if line.startswith("## "):
                line = f"**{line[3:]}**"

            # try and remove code blocks
            if line.strip().startswith("```"):
                if not code_block:
                    code_block = True
                    continue
                else:
                    code_block = False
                    continue
            if not code_block:
                output.append(line)
            if len(output) == max_lines:
                # in case a code block got through, make sure its closed
                if "".join(output).count("```") % 2 != 0:
                    output.append("```")
                output.append(f"`... and {len(body) - i} more lines`")
                break

        return "\n".join(output)

    async def send_issue(self, message: Message, issue):
        """Send a reply to a message with a formatted issue"""
        embed = Embed(title=f"Issue #{issue.number}: {issue.title}")
        embed.url = issue.html_url
        embed.set_footer(
            text=f"{issue.user.name if issue.user.name else issue.user.login}",
            icon_url=issue.user.avatar_url,
        )

        if issue.state == "closed":
            embed.description = "🚫 Closed"
            embed.color = MaterialColors.BLUE_GREY
        if issue.state == "open":
            if issue.locked:
                embed.description = "🔒 Locked"
                embed.color = MaterialColors.ORANGE
            else:
                embed.description = "🟢 Open"
                embed.color = MaterialColors.GREEN

        body = re.sub(r"<!--?.*-->", "", issue.body if issue.body else "_Empty_")

        embed.description += (
            f"{' - ' if len(issue.labels) != 0 else ''}{', '.join(f'``{l.name.capitalize()}``' for l in issue.labels)}\n"
            f"{self.assemble_body(body)}"
        )

        await self.reply(message, embeds=embed)

    async def send_snippet(self, message: Message):
        results = snippet_regex.findall(message.content)[0]

        lines = (
            [int(re.sub("[^0-9]", "", line)) for line in results[4].split("-")]
            if len(results) >= 5
            else None
        )
        if not lines:
            return
        user = results[0]
        repo = results[1]
        branch = results[2]
        file = results[3]
        extension = file.split(".")[-1]

        raw_url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{file}"

        async with aiohttp.ClientSession() as session:
            async with session.get(raw_url) as resp:
                if resp.status != 200:
                    return

                file_data = await resp.text()
                if file_data and lines:
                    lines[0] -= 1  # account for 0 based indexing
                    sample = file_data.split("\n")
                    if len(lines) == 2:
                        sample = sample[lines[0] :][: lines[1] - lines[0]]
                        file_data = "\n".join(sample)
                    else:
                        file_data = sample[lines[0]]

                embed = Embed(
                    title=f"{user}/{repo}",
                    description=f"```{extension}\n{textwrap.dedent(file_data)}```",
                )

                await self.reply(message, embeds=embed)

    @listen()
    async def on_message_create(self, event):
        message = event.message
        try:
            if message.author.bot:
                return
            in_data = message.content.lower()

            data = None
            try:
                if "github.com/" in in_data and "commit" in in_data:
                    print("commit detected")
                    return await self.get_commit(message)
                elif "github.com/" in in_data and "#l" in in_data:
                    print("searching for link")
                    return await self.send_snippet(message)
                elif data := re.search(r"(?:\s|^)#(\d{1,3})(?:\s|$)", in_data):
                    issue = await self.get_issue(self.repo, int(data.group(1)))
                    if not issue:
                        return
                    return await self.send_issue(message, issue)
            except github.UnknownObjectException:
                print(f"No git object with id: {data.group().split('#')[-1]}")
        except github.GithubException:
            pass
        except Exception as e:
            print("".join(traceback.format_exception(type(e), e, e.__traceback__)))


def setup(bot):
    GithubMessages(bot)