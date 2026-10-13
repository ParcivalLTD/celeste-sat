using System;
using System.Collections;
using System.Runtime.CompilerServices;
using Microsoft.Xna.Framework;
using Monocle;

namespace Celeste;

public class SwitchGate : Solid
{
	public static ParticleType P_Behind;

	public static ParticleType P_Dust;

	private MTexture[,] nineSlice;

	private Sprite icon;

	private Vector2 iconOffset;

	private Wiggler wiggler;

	private Vector2 node;

	private SoundSource openSfx;

	private bool persistent;

	private Color inactiveColor = Calc.HexToColor("5fcde4");

	private Color activeColor = Color.White;

	private Color finishColor = Calc.HexToColor("f141df");

	[MethodImpl(MethodImplOptions.NoInlining)]
	public SwitchGate(Vector2 position, float width, float height, Vector2 node, bool persistent, string spriteName)
		: base(position, width, height, safe: false)
	{
		this.node = node;
		this.persistent = persistent;
		Add(icon = new Sprite(GFX.Game, "objects/switchgate/icon"));
		icon.Add("spin", "", 0.1f, "spin");
		icon.Play("spin");
		icon.Rate = 0f;
		icon.Color = inactiveColor;
		icon.Position = (iconOffset = new Vector2(width / 2f, height / 2f));
		icon.CenterOrigin();
		Add(wiggler = Wiggler.Create(0.5f, 4f, [MethodImpl(MethodImplOptions.NoInlining)] (float f) =>
		{
			icon.Scale = Vector2.One * (1f + f);
		}));
		MTexture mTexture = GFX.Game["objects/switchgate/" + spriteName];
		nineSlice = new MTexture[3, 3];
		for (int num = 0; num < 3; num++)
		{
			for (int num2 = 0; num2 < 3; num2++)
			{
				nineSlice[num, num2] = mTexture.GetSubtexture(new Rectangle(num * 8, num2 * 8, 8, 8));
			}
		}
		Add(openSfx = new SoundSource());
		Add(new LightOcclude(0.5f));
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	public SwitchGate(EntityData data, Vector2 offset)
		: this(data.Position + offset, data.Width, data.Height, data.Nodes[0] + offset, data.Bool("persistent"), data.Attr("sprite", "block"))
	{
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	public override void Awake(Scene scene)
	{
		base.Awake(scene);
		if (Switch.CheckLevelFlag(SceneAs<Level>()))
		{
			MoveTo(node);
			icon.Rate = 0f;
			icon.SetAnimationFrame(0);
			icon.Color = finishColor;
		}
		else
		{
			Add(new Coroutine(Sequence(node)));
		}
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	public override void Render()
	{
		float num = Collider.Width / 8f - 1f;
		float num2 = Collider.Height / 8f - 1f;
		for (int i = 0; (float)i <= num; i++)
		{
			for (int j = 0; (float)j <= num2; j++)
			{
				int num3 = (((float)i < num) ? Math.Min(i, 1) : 2);
				int num4 = (((float)j < num2) ? Math.Min(j, 1) : 2);
				nineSlice[num3, num4].Draw(Position + Shake + new Vector2(i * 8, j * 8));
			}
		}
		icon.Position = iconOffset + Shake;
		icon.DrawOutline();
		base.Render();
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	private IEnumerator Sequence(Vector2 node)
	{
		Vector2 start = Position;
		while (!Switch.Check(Scene))
		{
			yield return null;
		}
		if (persistent)
		{
			Switch.SetLevelFlag(SceneAs<Level>());
		}
		yield return 0.1f;
		openSfx.Play("event:/game/general/touchswitch_gate_open");
		StartShaking(0.5f);
		while (icon.Rate < 1f)
		{
			icon.Color = Color.Lerp(inactiveColor, activeColor, icon.Rate);
			icon.Rate += Engine.DeltaTime * 2f;
			yield return null;
		}
		yield return 0.1f;
		int particleAt = 0;
		Tween tween = Tween.Create(Tween.TweenMode.Oneshot, Ease.CubeOut, 2f, start: true);
		tween.OnUpdate = [MethodImpl(MethodImplOptions.NoInlining)] (Tween t) =>
		{
			MoveTo(Vector2.Lerp(start, node, t.Eased));
			if (Scene.OnInterval(0.1f))
			{
				particleAt++;
				particleAt %= 2;
				for (int i = 0; (float)i < Width / 8f; i++)
				{
					for (int j = 0; (float)j < Height / 8f; j++)
					{
						if ((i + j) % 2 == particleAt)
						{
							SceneAs<Level>().ParticlesBG.Emit(P_Behind, Position + new Vector2(i * 8, j * 8) + Calc.Random.Range(Vector2.One * 2f, Vector2.One * 6f));
						}
					}
				}
			}
		};
		Add(tween);
		yield return 1.8f;
		bool collidable = Collidable;
		Collidable = false;
		if (node.X <= start.X)
		{
			Vector2 vector = new Vector2(0f, 2f);
			for (int num = 0; (float)num < Height / 8f; num++)
			{
				Vector2 vector2 = new Vector2(Left - 1f, Top + 4f + (float)(num * 8));
				Vector2 point = vector2 + Vector2.UnitX;
				if (Scene.CollideCheck<Solid>(vector2) && !Scene.CollideCheck<Solid>(point))
				{
					SceneAs<Level>().ParticlesFG.Emit(P_Dust, vector2 + vector, (float)Math.PI);
					SceneAs<Level>().ParticlesFG.Emit(P_Dust, vector2 - vector, (float)Math.PI);
				}
			}
		}
		if (node.X >= start.X)
		{
			Vector2 vector3 = new Vector2(0f, 2f);
			for (int num2 = 0; (float)num2 < Height / 8f; num2++)
			{
				Vector2 vector4 = new Vector2(Right + 1f, Top + 4f + (float)(num2 * 8));
				Vector2 point2 = vector4 - Vector2.UnitX * 2f;
				if (Scene.CollideCheck<Solid>(vector4) && !Scene.CollideCheck<Solid>(point2))
				{
					SceneAs<Level>().ParticlesFG.Emit(P_Dust, vector4 + vector3, 0f);
					SceneAs<Level>().ParticlesFG.Emit(P_Dust, vector4 - vector3, 0f);
				}
			}
		}
		if (node.Y <= start.Y)
		{
			Vector2 vector5 = new Vector2(2f, 0f);
			for (int num3 = 0; (float)num3 < Width / 8f; num3++)
			{
				Vector2 vector6 = new Vector2(Left + 4f + (float)(num3 * 8), Top - 1f);
				Vector2 point3 = vector6 + Vector2.UnitY;
				if (Scene.CollideCheck<Solid>(vector6) && !Scene.CollideCheck<Solid>(point3))
				{
					SceneAs<Level>().ParticlesFG.Emit(P_Dust, vector6 + vector5, -(float)Math.PI / 2f);
					SceneAs<Level>().ParticlesFG.Emit(P_Dust, vector6 - vector5, -(float)Math.PI / 2f);
				}
			}
		}
		if (node.Y >= start.Y)
		{
			Vector2 vector7 = new Vector2(2f, 0f);
			for (int num4 = 0; (float)num4 < Width / 8f; num4++)
			{
				Vector2 vector8 = new Vector2(Left + 4f + (float)(num4 * 8), Bottom + 1f);
				Vector2 point4 = vector8 - Vector2.UnitY * 2f;
				if (Scene.CollideCheck<Solid>(vector8) && !Scene.CollideCheck<Solid>(point4))
				{
					SceneAs<Level>().ParticlesFG.Emit(P_Dust, vector8 + vector7, (float)Math.PI / 2f);
					SceneAs<Level>().ParticlesFG.Emit(P_Dust, vector8 - vector7, (float)Math.PI / 2f);
				}
			}
		}
		Collidable = collidable;
		Audio.Play("event:/game/general/touchswitch_gate_finish", Position);
		StartShaking(0.2f);
		while (icon.Rate > 0f)
		{
			icon.Color = Color.Lerp(activeColor, finishColor, 1f - icon.Rate);
			icon.Rate -= Engine.DeltaTime * 4f;
			yield return null;
		}
		icon.Rate = 0f;
		icon.SetAnimationFrame(0);
		wiggler.Start();
		bool collidable2 = Collidable;
		Collidable = false;
		if (!Scene.CollideCheck<Solid>(Center))
		{
			for (int num5 = 0; num5 < 32; num5++)
			{
				float num6 = Calc.Random.NextFloat((float)Math.PI * 2f);
				SceneAs<Level>().ParticlesFG.Emit(TouchSwitch.P_Fire, Position + iconOffset + Calc.AngleToVector(num6, 4f), num6);
			}
		}
		Collidable = collidable2;
	}
}
