using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Runtime.CompilerServices;
using System.Text.RegularExpressions;
using System.Threading;
using System.Xml;
using Celeste.Mod;
using Celeste.Mod.Core;
using Celeste.Mod.Helpers;
using Celeste.Mod.Meta;
using Celeste.Mod.UI;
using Microsoft.Xna.Framework;
using MonoMod;
using Monocle;

namespace Celeste;

public class LevelLoader : Scene
{
	private Session session;

	private Vector2? startPosition;

	private bool started;

	public Player.IntroTypes? PlayerIntroTypeOverride;

	private static WeakReference<Thread> LastLoadingThread;

	public Level Level { get; private set; }

	public bool Loaded { get; private set; }

	[MethodImpl(MethodImplOptions.NoInlining)]
	public LevelLoader(Session session, Vector2? startPosition = null)
	{
		string text = session?.Area.GetSID() ?? "NULL";
		object obj;
		string name;
		if (session != null)
		{
			_ = session.Area;
			if (Dialog.Has(name = AreaData.Get(session.Area).Name))
			{
				obj = " [" + Dialog.Clean(name, Dialog.Languages["english"]) + "]";
				goto IL_0066;
			}
		}
		obj = null;
		goto IL_0066;
		IL_0066:
		name = (string)obj;
		if (session != null && session.Area.Mode > AreaMode.Normal)
		{
			name += $" [{session.Area.Mode}]";
		}
		string text2 = "LevelLoader";
		string tag = text2;
		Logger.LogInterpolatedStringHandler<LogLevelConstTypes.Info> str = new Logger.LogInterpolatedStringHandler<LogLevelConstTypes.Info>(8, 2, text2, out var shouldLog);
		if (shouldLog)
		{
			str.AppendLiteral("Loading ");
			str.AppendFormatted(text);
			str.AppendFormatted(name);
		}
		Logger.Info(tag, str);
		if (LastLoadingThread != null && LastLoadingThread.TryGetTarget(out var target) && target != null && target.IsAlive)
		{
			target?.Interrupt();
		}
		if (CoreModule.Settings.LazyLoading)
		{
			MainThreadHelper.Schedule(() =>
			{
				VirtualContent.UnloadOverworld();
			});
		}
		SurfaceIndex.TileToIndex = new Dictionary<char, int>
		{
			{ '1', 3 },
			{ '3', 4 },
			{ '4', 7 },
			{ '5', 8 },
			{ '6', 8 },
			{ '7', 8 },
			{ '8', 8 },
			{ '9', 13 },
			{ 'a', 8 },
			{ 'b', 23 },
			{ 'c', 8 },
			{ 'd', 8 },
			{ 'e', 8 },
			{ 'f', 8 },
			{ 'g', 8 },
			{ 'G', 8 },
			{ 'h', 33 },
			{ 'i', 4 },
			{ 'j', 8 },
			{ 'k', 3 },
			{ 'l', 25 },
			{ 'm', 44 },
			{ 'n', 40 },
			{ 'o', 43 }
		};
		SurfaceIndex.IndexToCustomPath.Clear();
		SurfaceIndex.IndexToSoundParam.Clear();
		string text3 = "";
		try
		{
			MapMeta meta = AreaData.Get(session).Meta;
			text3 = meta?.BackgroundTiles;
			if (string.IsNullOrEmpty(text3))
			{
				text3 = Path.Combine("Graphics", "BackgroundTiles.xml");
			}
			GFX.BGAutotiler = new Autotiler(text3);
			text3 = meta?.ForegroundTiles;
			if (string.IsNullOrEmpty(text3))
			{
				text3 = Path.Combine("Graphics", "ForegroundTiles.xml");
			}
			GFX.FGAutotiler = new Autotiler(text3);
			text3 = meta?.AnimatedTiles;
			if (string.IsNullOrEmpty(text3))
			{
				text3 = Path.Combine("Graphics", "AnimatedTiles.xml");
			}
			GFX.AnimatedTilesBank = new AnimatedTilesBank();
			foreach (XmlElement item in Calc.LoadContentXML(text3).GetElementsByTagName("sprite"))
			{
				if (item != null)
				{
					GFX.AnimatedTilesBank.Add(item.Attr("name"), item.AttrFloat("delay", 0f), item.AttrVector2("posX", "posY", Vector2.Zero), item.AttrVector2("origX", "origY", Vector2.Zero), GFX.Game.GetAtlasSubtextures(item.Attr("path")));
				}
			}
			GFX.SpriteBank = new SpriteBank(GFX.Game, Path.Combine("Graphics", "Sprites.xml"));
			text3 = meta?.Sprites;
			if (!string.IsNullOrEmpty(text3))
			{
				SpriteBank spriteBank = GFX.SpriteBank;
				foreach (KeyValuePair<string, SpriteData> spriteDatum in new SpriteBank(GFX.Game, getModdedSpritesXml(text3)).SpriteData)
				{
					string key = spriteDatum.Key;
					SpriteData value = spriteDatum.Value;
					if (spriteBank.SpriteData.TryGetValue(key, out var value2))
					{
						bool flag = false;
						bool flag2 = false;
						for (int num = value.Sources.Count - 1; num >= 0; num--)
						{
							XmlElement xML = value.Sources[num].XML;
							if (xML != null)
							{
								if (!flag)
								{
									if (xML.HasChild("Center"))
									{
										value2.Sprite.CenterOrigin();
										value2.Sprite.Justify = new Vector2(0.5f, 0.5f);
										flag = true;
									}
									else if (xML.HasChild("Justify"))
									{
										value2.Sprite.JustifyOrigin(xML.ChildPosition("Justify"));
										value2.Sprite.Justify = xML.ChildPosition("Justify");
										flag = true;
									}
									else if (xML.HasChild("Origin"))
									{
										value2.Sprite.Origin = xML.ChildPosition("Origin");
										flag = true;
									}
								}
								if (!flag2 && xML.HasChild("Position"))
								{
									value2.Sprite.Position = xML.ChildPosition("Position");
									flag2 = true;
								}
								if (flag & flag2)
								{
									break;
								}
							}
						}
						IDictionary animations = value2.Sprite.Animations;
						foreach (DictionaryEntry item2 in (IDictionary)value.Sprite.Animations)
						{
							animations[item2.Key] = item2.Value;
						}
						value2.Sources.AddRange(value.Sources);
						value2.Sprite.Stop();
						if (value.Sprite.CurrentAnimationID != "")
						{
							value2.Sprite.Play(value.Sprite.CurrentAnimationID);
						}
					}
					else
					{
						spriteBank.SpriteData[key] = value;
					}
				}
			}
			PlayerSprite.ClearFramesMetadata();
			PlayerSprite.CreateFramesMetadata("player");
			PlayerSprite.CreateFramesMetadata("player_no_backpack");
			PlayerSprite.CreateFramesMetadata("badeline");
			PlayerSprite.CreateFramesMetadata("player_badeline");
			PlayerSprite.CreateFramesMetadata("player_playback");
			text3 = meta?.Portraits;
			if (string.IsNullOrEmpty(text3))
			{
				text3 = Path.Combine("Graphics", "Portraits.xml");
			}
			GFX.PortraitsSpriteBank = new SpriteBank(GFX.Portraits, text3);
		}
		catch (Exception ex)
		{
			Logger.LogInterpolatedStringHandler<LogLevelConstTypes.Warn> str2;
			if (LevelEnter.ErrorMessage == null)
			{
				if (ex is XmlException)
				{
					LevelEnter.ErrorMessage = Dialog.Get("postcard_xmlerror").Replace("((path))", text3);
					text2 = "LevelLoader";
					string tag2 = text2;
					str2 = new Logger.LogInterpolatedStringHandler<LogLevelConstTypes.Warn>(15, 1, text2, out shouldLog);
					if (shouldLog)
					{
						str2.AppendLiteral("Failed parsing ");
						str2.AppendFormatted(text3);
					}
					Logger.Warn(tag2, str2);
				}
				else if (ex.TypeInStacktrace(typeof(Autotiler)))
				{
					LevelEnter.ErrorMessage = Dialog.Get("postcard_tilexmlerror").Replace("((path))", text3);
					text2 = "LevelLoader";
					string tag3 = text2;
					str2 = new Logger.LogInterpolatedStringHandler<LogLevelConstTypes.Warn>(30, 1, text2, out shouldLog);
					if (shouldLog)
					{
						str2.AppendLiteral("Failed parsing tileset tag in ");
						str2.AppendFormatted(text3);
					}
					Logger.Warn(tag3, str2);
				}
				else
				{
					LevelEnter.ErrorMessage = Dialog.Get("postcard_levelloadfailed").Replace("((sid))", text);
				}
			}
			text2 = "LevelLoader";
			string tag4 = text2;
			str2 = new Logger.LogInterpolatedStringHandler<LogLevelConstTypes.Warn>(15, 2, text2, out shouldLog);
			if (shouldLog)
			{
				str2.AppendLiteral("Failed loading ");
				str2.AppendFormatted(text);
				str2.AppendFormatted(name);
			}
			Logger.Warn(tag4, str2);
			Logger.LogDetailed(ex);
		}
		orig_ctor(session, startPosition);
		if (LevelEnter.ErrorMessage == null)
		{
			RunThread.Start(LoadingThread_Safe, "LEVEL_LOADER");
			LastLoadingThread = RunThread.Current;
			{
				foreach (Queue<Entity> value3 in Engine.Pooler.Pools.Values)
				{
					value3.Clear();
				}
				return;
			}
		}
		Loaded = true;
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	[PatchLoadingThreadAddEvent]
	[PatchLoadingThreadAddSubHudRenderer]
	[PatchLoadingThreadForMapMetadata]
	private void LoadingThread()
	{
		MapData mapData = session.MapData;
		AreaData areaData = AreaData.Get(session);
		if (session.Area.ID == 0)
		{
			SaveData.Instance.Assists.DashMode = Assists.DashModes.Normal;
		}
		Level.Add(Level.GameplayRenderer = new GameplayRenderer());
		Level.Add(Level.Lighting = new LightingRenderer());
		Level.Add(Level.Bloom = new BloomRenderer());
		Level.Add(Level.Displacement = new DisplacementRenderer());
		Level.Add(Level.Background = new BackdropRenderer());
		Level.Add(Level.Foreground = new BackdropRenderer());
		Level.Add(new DustEdges());
		Level.Add(new WaterSurface());
		Level.Add(new MirrorSurfaces());
		Level.Add(new GlassBlockBg());
		Level.Add(new LightningRenderer());
		Level.Add(new SeekerBarrierRenderer());
		Level.Add(Level.SubHudRenderer = new SubHudRenderer());
		Level.Add(Level.HudRenderer = new HudRenderer());
		if (session.Area.ID == 9 || _ShouldAddIceTileOverlay(mapData))
		{
			Level.Add(new IceTileOverlay());
		}
		Level.BaseLightingAlpha = (Level.Lighting.Alpha = areaData.DarknessAlpha);
		Level.Bloom.Base = areaData.BloomBase;
		Level.Bloom.Strength = areaData.BloomStrength;
		Level.BackgroundColor = mapData.BackgroundColor;
		Level.Background.Backdrops = mapData.CreateBackdrops(mapData.Background);
		foreach (Backdrop backdrop in Level.Background.Backdrops)
		{
			backdrop.Renderer = Level.Background;
		}
		Level.Foreground.Backdrops = mapData.CreateBackdrops(mapData.Foreground);
		foreach (Backdrop backdrop2 in Level.Foreground.Backdrops)
		{
			backdrop2.Renderer = Level.Foreground;
		}
		Level.RendererList.UpdateLists();
		Level.Add(Level.FormationBackdrop = new FormationBackdrop());
		Level.Camera = Level.GameplayRenderer.Camera;
		Audio.SetCamera(Level.Camera);
		Level.Session = session;
		SaveData.Instance.StartSession(Level.Session);
		Level.Particles = new ParticleSystem(-8000, 400);
		Level.Particles.Tag = Tags.Global;
		Level.Add(Level.Particles);
		Level.ParticlesBG = new ParticleSystem(8000, 400);
		Level.ParticlesBG.Tag = Tags.Global;
		Level.Add(Level.ParticlesBG);
		Level.ParticlesFG = new ParticleSystem(-50000, 800);
		Level.ParticlesFG.Tag = Tags.Global;
		Level.ParticlesFG.Add(new MirrorReflection());
		Level.Add(Level.ParticlesFG);
		Level.Add(Level.strawberriesDisplay = new TotalStrawberriesDisplay());
		Level.Add(new SpeedrunTimerDisplay());
		Level.Add(new GameplayStats());
		Level.Add(new GrabbyIcon());
		Rectangle tileBounds = mapData.TileBounds;
		GFX.FGAutotiler.LevelBounds.Clear();
		VirtualMap<char> virtualMap = new VirtualMap<char>(tileBounds.Width, tileBounds.Height, '0');
		VirtualMap<char> virtualMap2 = new VirtualMap<char>(tileBounds.Width, tileBounds.Height, '0');
		VirtualMap<bool> virtualMap3 = new VirtualMap<bool>(tileBounds.Width, tileBounds.Height, emptyValue: false);
		Regex regex = new Regex("\\r\\n|\\n\\r|\\n|\\r");
		foreach (LevelData level in mapData.Levels)
		{
			int left = level.TileBounds.Left;
			int top = level.TileBounds.Top;
			string[] array = regex.Split(level.Bg);
			for (int i = top; i < top + array.Length; i++)
			{
				for (int j = left; j < left + array[i - top].Length; j++)
				{
					virtualMap[j - tileBounds.X, i - tileBounds.Y] = array[i - top][j - left];
				}
			}
			string[] array2 = regex.Split(level.Solids);
			for (int k = top; k < top + array2.Length; k++)
			{
				for (int l = left; l < left + array2[k - top].Length; l++)
				{
					virtualMap2[l - tileBounds.X, k - tileBounds.Y] = array2[k - top][l - left];
				}
			}
			for (int m = level.TileBounds.Left; m < level.TileBounds.Right; m++)
			{
				for (int n = level.TileBounds.Top; n < level.TileBounds.Bottom; n++)
				{
					virtualMap3[m - tileBounds.Left, n - tileBounds.Top] = true;
				}
			}
			GFX.FGAutotiler.LevelBounds.Add(new Rectangle(level.TileBounds.X - tileBounds.X, level.TileBounds.Y - tileBounds.Y, level.TileBounds.Width, level.TileBounds.Height));
		}
		foreach (Rectangle item in mapData.Filler)
		{
			for (int num = item.Left; num < item.Right; num++)
			{
				for (int num2 = item.Top; num2 < item.Bottom; num2++)
				{
					char c = '0';
					if (item.Top - tileBounds.Y > 0)
					{
						char c2 = virtualMap2[num - tileBounds.X, item.Top - tileBounds.Y - 1];
						if (c2 != '0')
						{
							c = c2;
						}
					}
					if (c == '0' && item.Left - tileBounds.X > 0)
					{
						char c3 = virtualMap2[item.Left - tileBounds.X - 1, num2 - tileBounds.Y];
						if (c3 != '0')
						{
							c = c3;
						}
					}
					if (c == '0' && item.Right - tileBounds.X < tileBounds.Width - 1)
					{
						char c4 = virtualMap2[item.Right - tileBounds.X, num2 - tileBounds.Y];
						if (c4 != '0')
						{
							c = c4;
						}
					}
					if (c == '0' && item.Bottom - tileBounds.Y < tileBounds.Height - 1)
					{
						char c5 = virtualMap2[num - tileBounds.X, item.Bottom - tileBounds.Y];
						if (c5 != '0')
						{
							c = c5;
						}
					}
					if (c == '0')
					{
						c = '1';
					}
					virtualMap2[num - tileBounds.X, num2 - tileBounds.Y] = c;
					virtualMap3[num - tileBounds.X, num2 - tileBounds.Y] = true;
				}
			}
		}
		foreach (LevelData level2 in mapData.Levels)
		{
			for (int num3 = level2.TileBounds.Left; num3 < level2.TileBounds.Right; num3++)
			{
				int top2 = level2.TileBounds.Top;
				char value = virtualMap[num3 - tileBounds.X, top2 - tileBounds.Y];
				for (int num4 = 1; num4 < 4 && !virtualMap3[num3 - tileBounds.X, top2 - tileBounds.Y - num4]; num4++)
				{
					virtualMap[num3 - tileBounds.X, top2 - tileBounds.Y - num4] = value;
				}
				top2 = level2.TileBounds.Bottom - 1;
				char value2 = virtualMap[num3 - tileBounds.X, top2 - tileBounds.Y];
				for (int num5 = 1; num5 < 4 && !virtualMap3[num3 - tileBounds.X, top2 - tileBounds.Y + num5]; num5++)
				{
					virtualMap[num3 - tileBounds.X, top2 - tileBounds.Y + num5] = value2;
				}
			}
			for (int num6 = level2.TileBounds.Top - 4; num6 < level2.TileBounds.Bottom + 4; num6++)
			{
				int left2 = level2.TileBounds.Left;
				char value3 = virtualMap[left2 - tileBounds.X, num6 - tileBounds.Y];
				for (int num7 = 1; num7 < 4 && !virtualMap3[left2 - tileBounds.X - num7, num6 - tileBounds.Y]; num7++)
				{
					virtualMap[left2 - tileBounds.X - num7, num6 - tileBounds.Y] = value3;
				}
				left2 = level2.TileBounds.Right - 1;
				char value4 = virtualMap[left2 - tileBounds.X, num6 - tileBounds.Y];
				for (int num8 = 1; num8 < 4 && !virtualMap3[left2 - tileBounds.X + num8, num6 - tileBounds.Y]; num8++)
				{
					virtualMap[left2 - tileBounds.X + num8, num6 - tileBounds.Y] = value4;
				}
			}
		}
		foreach (LevelData level3 in mapData.Levels)
		{
			for (int num9 = level3.TileBounds.Left; num9 < level3.TileBounds.Right; num9++)
			{
				int top3 = level3.TileBounds.Top;
				if (virtualMap2[num9 - tileBounds.X, top3 - tileBounds.Y] == '0')
				{
					for (int num10 = 1; num10 < 8; num10++)
					{
						virtualMap3[num9 - tileBounds.X, top3 - tileBounds.Y - num10] = true;
					}
				}
				top3 = level3.TileBounds.Bottom - 1;
				if (virtualMap2[num9 - tileBounds.X, top3 - tileBounds.Y] == '0')
				{
					for (int num11 = 1; num11 < 8; num11++)
					{
						virtualMap3[num9 - tileBounds.X, top3 - tileBounds.Y + num11] = true;
					}
				}
			}
		}
		foreach (LevelData level4 in mapData.Levels)
		{
			for (int num12 = level4.TileBounds.Left; num12 < level4.TileBounds.Right; num12++)
			{
				int top4 = level4.TileBounds.Top;
				char value5 = virtualMap2[num12 - tileBounds.X, top4 - tileBounds.Y];
				for (int num13 = 1; num13 < 4 && !virtualMap3[num12 - tileBounds.X, top4 - tileBounds.Y - num13]; num13++)
				{
					virtualMap2[num12 - tileBounds.X, top4 - tileBounds.Y - num13] = value5;
				}
				top4 = level4.TileBounds.Bottom - 1;
				char value6 = virtualMap2[num12 - tileBounds.X, top4 - tileBounds.Y];
				for (int num14 = 1; num14 < 4 && !virtualMap3[num12 - tileBounds.X, top4 - tileBounds.Y + num14]; num14++)
				{
					virtualMap2[num12 - tileBounds.X, top4 - tileBounds.Y + num14] = value6;
				}
			}
			for (int num15 = level4.TileBounds.Top - 4; num15 < level4.TileBounds.Bottom + 4; num15++)
			{
				int left3 = level4.TileBounds.Left;
				char value7 = virtualMap2[left3 - tileBounds.X, num15 - tileBounds.Y];
				for (int num16 = 1; num16 < 4 && !virtualMap3[left3 - tileBounds.X - num16, num15 - tileBounds.Y]; num16++)
				{
					virtualMap2[left3 - tileBounds.X - num16, num15 - tileBounds.Y] = value7;
				}
				left3 = level4.TileBounds.Right - 1;
				char value8 = virtualMap2[left3 - tileBounds.X, num15 - tileBounds.Y];
				for (int num17 = 1; num17 < 4 && !virtualMap3[left3 - tileBounds.X + num17, num15 - tileBounds.Y]; num17++)
				{
					virtualMap2[left3 - tileBounds.X + num17, num15 - tileBounds.Y] = value8;
				}
			}
		}
		Vector2 position = new Vector2(tileBounds.X, tileBounds.Y) * 8f;
		Calc.PushRandom(mapData.LoadSeed);
		BackgroundTiles backgroundTiles = null;
		SolidTiles solidTiles = null;
		Level.Add(Level.BgTiles = (backgroundTiles = new BackgroundTiles(position, virtualMap)));
		Level.Add(Level.SolidTiles = (solidTiles = new SolidTiles(position, virtualMap2)));
		Level.BgData = virtualMap;
		Level.SolidsData = virtualMap2;
		Calc.PopRandom();
		new Entity(position).Add(Level.FgTilesLightMask = new TileGrid(8, 8, tileBounds.Width, tileBounds.Height));
		Level.FgTilesLightMask.Color = Color.Black;
		foreach (LevelData level5 in mapData.Levels)
		{
			int left4 = level5.TileBounds.Left;
			int top5 = level5.TileBounds.Top;
			int width = level5.TileBounds.Width;
			int height = level5.TileBounds.Height;
			if (!string.IsNullOrEmpty(level5.BgTiles))
			{
				int[,] tiles = Calc.ReadCSVIntGrid(level5.BgTiles, width, height);
				backgroundTiles.Tiles.Overlay(GFX.SceneryTiles, tiles, left4 - tileBounds.X, top5 - tileBounds.Y);
			}
			if (!string.IsNullOrEmpty(level5.FgTiles))
			{
				int[,] tiles2 = Calc.ReadCSVIntGrid(level5.FgTiles, width, height);
				solidTiles.Tiles.Overlay(GFX.SceneryTiles, tiles2, left4 - tileBounds.X, top5 - tileBounds.Y);
				Level.FgTilesLightMask.Overlay(GFX.SceneryTiles, tiles2, left4 - tileBounds.X, top5 - tileBounds.Y);
			}
		}
		if (areaData.OnLevelBegin != null)
		{
			areaData.OnLevelBegin(Level);
		}
		Level.StartPosition = startPosition;
		Level.Pathfinder = new Pathfinder(Level);
		Everest.Events.LevelLoader.LoadingThread(Level);
		Loaded = true;
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	private void StartLevel()
	{
		started = true;
		Session session = Level.Session;
		Player.IntroTypes playerIntro = (PlayerIntroTypeOverride.HasValue ? PlayerIntroTypeOverride.Value : ((!session.FirstLevel || !session.StartedFromBeginning || !session.JustStarted) ? Player.IntroTypes.Respawn : ((session.Area.Mode != AreaMode.CSide) ? AreaData.Get(Level).IntroType : Player.IntroTypes.WalkInRight)));
		Level.LoadLevel(playerIntro, isFromLoader: true);
		Level.Session.JustStarted = false;
		if (Engine.Scene == this)
		{
			Engine.Scene = Level;
		}
	}

	public override void Update()
	{
		base.Update();
		if (!Loaded || started)
		{
			return;
		}
		if (LevelEnter.ErrorMessage == null)
		{
			try
			{
				StartLevel();
				return;
			}
			catch (Exception e)
			{
				string sID = session.Area.GetSID();
				string text = (Dialog.Has(text = AreaData.Get(session.Area).Name) ? (" [" + Dialog.Clean(text, Dialog.Languages["english"]) + "]") : null);
				if (session.Area.Mode > AreaMode.Normal)
				{
					text += $" [{session.Area.Mode}]";
				}
				LevelEnter.ErrorMessage = Dialog.Get("postcard_levelloadfailed").Replace("((sid))", sID);
				string tag = "LevelLoader";
				Logger.LogInterpolatedStringHandler<LogLevelConstTypes.Warn> str = new Logger.LogInterpolatedStringHandler<LogLevelConstTypes.Warn>(36, 3, tag, out var shouldLog);
				if (shouldLog)
				{
					str.AppendLiteral("Failed Starting Level at room ");
					str.AppendFormatted(session.Level);
					str.AppendLiteral(" of '");
					str.AppendFormatted(sID);
					str.AppendFormatted(text);
					str.AppendLiteral("'");
				}
				Logger.Warn(tag, str);
				Logger.LogDetailed(e);
				LevelEnter.Go(session, fromSaveData: false);
				return;
			}
		}
		LevelEnter.Go(session, fromSaveData: false);
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	[PatchLevelLoaderOrigCtor]
	public void orig_ctor(Session session, Vector2? startPosition = null)
	{
		base..ctor();
		this.session = session;
		if (!startPosition.HasValue)
		{
			this.startPosition = session.RespawnPoint;
		}
		else
		{
			this.startPosition = startPosition;
		}
		Level = new Level();
	}

	private XmlDocument getModdedSpritesXml(string path)
	{
		XmlDocument vanillaSpritesXml = Calc.orig_LoadContentXML(Path.Combine("Graphics", "Sprites.xml"));
		XmlDocument modSpritesXml = Calc.LoadContentXML(path);
		return SpriteBank.GetSpriteBankExcludingVanillaCopyPastes(vanillaSpritesXml, modSpritesXml, path);
	}

	private void LoadingThread_Safe()
	{
		try
		{
			LoadingThread();
		}
		catch (Exception ex)
		{
			string text = this.session?.Area.GetSID() ?? "NULL";
			Session session = this.session;
			object obj;
			string name;
			if (session != null)
			{
				_ = session.Area;
				if (true && Dialog.Has(name = AreaData.Get(this.session.Area).Name))
				{
					obj = " [" + Dialog.Clean(name, Dialog.Languages["english"]) + "]";
					goto IL_0089;
				}
			}
			obj = null;
			goto IL_0089;
			IL_0089:
			name = (string)obj;
			Session session2 = this.session;
			if (session2 != null && session2.Area.Mode > AreaMode.Normal)
			{
				name += $" [{this.session.Area.Mode}]";
			}
			bool shouldLog;
			string text3;
			Logger.LogInterpolatedStringHandler<LogLevelConstTypes.Warn> str;
			if (LevelEnter.ErrorMessage == null)
			{
				if (ex is AutotilerException ex2 && ex.Source == "TileHandler")
				{
					string text2 = "???";
					for (int i = 0; i < GFX.FGAutotiler.LevelBounds.Count; i++)
					{
						if (GFX.FGAutotiler.LevelBounds[i].Contains(ex2.X, ex2.Y))
						{
							ex2.X -= GFX.FGAutotiler.LevelBounds[i].X;
							ex2.Y -= GFX.FGAutotiler.LevelBounds[i].Y;
							text2 = this.session.MapData.Levels[i].Name;
							break;
						}
					}
					string newValue = "";
					if (ex.TypeInStacktrace(typeof(SolidTiles)))
					{
						newValue = "fg";
					}
					else if (ex.TypeInStacktrace(typeof(BackgroundTiles)))
					{
						newValue = "bg";
					}
					LevelEnter.ErrorMessage = Dialog.Get("postcard_badtileid").Replace("((type))", newValue).Replace("((id))", ex2.ID.ToString())
						.Replace("((x))", ex2.X.ToString())
						.Replace("((y))", ex2.Y.ToString())
						.Replace("((room))", text2)
						.Replace("((sid))", text);
					text3 = "LevelLoader";
					string tag = text3;
					str = new Logger.LogInterpolatedStringHandler<LogLevelConstTypes.Warn>(37, 4, text3, out shouldLog);
					if (shouldLog)
					{
						str.AppendLiteral("Undefined tile id '");
						str.AppendFormatted(ex2.ID);
						str.AppendLiteral("' at (");
						str.AppendFormatted(ex2.X);
						str.AppendLiteral(", ");
						str.AppendFormatted(ex2.Y);
						str.AppendLiteral(") in room ");
						str.AppendFormatted(text2);
					}
					Logger.Warn(tag, str);
				}
				else
				{
					LevelEnter.ErrorMessage = Dialog.Get("postcard_levelloadfailed").Replace("((sid))", text);
				}
			}
			text3 = "LevelLoader";
			string tag2 = text3;
			str = new Logger.LogInterpolatedStringHandler<LogLevelConstTypes.Warn>(15, 2, text3, out shouldLog);
			if (shouldLog)
			{
				str.AppendLiteral("Failed loading ");
				str.AppendFormatted(text);
				str.AppendFormatted(name);
			}
			Logger.Warn(tag2, str);
			Logger.LogDetailed(ex);
			Loaded = true;
		}
	}

	private static bool _ShouldAddIceTileOverlay(MapData mapData)
	{
		return mapData.Meta?.CoreModeIceTileOverlay == true;
	}
}
