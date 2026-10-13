using System;
using System.Runtime.CompilerServices;
using Monocle;

namespace Celeste;

[Tracked(false)]
public class Switch : Component
{
	public bool GroundReset;

	public Action OnActivate;

	public Action OnDeactivate;

	public Action OnFinish;

	public Action OnStartFinished;

	public bool Activated { get; private set; }

	public bool Finished { get; private set; }

	public Switch(bool groundReset)
		: base(active: true, visible: false)
	{
		GroundReset = groundReset;
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	public override void EntityAdded(Scene scene)
	{
		base.EntityAdded(scene);
		if (CheckLevelFlag(SceneAs<Level>()))
		{
			StartFinished();
		}
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	public override void Update()
	{
		base.Update();
		if (GroundReset && Activated && !Finished)
		{
			Player entity = Scene.Tracker.GetEntity<Player>();
			if (entity != null && entity.OnGround())
			{
				Deactivate();
			}
		}
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	public bool Activate()
	{
		if (!Finished && !Activated)
		{
			Activated = true;
			if (OnActivate != null)
			{
				OnActivate();
			}
			return FinishedCheck(SceneAs<Level>());
		}
		return false;
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	public void Deactivate()
	{
		if (!Finished && Activated)
		{
			Activated = false;
			if (OnDeactivate != null)
			{
				OnDeactivate();
			}
		}
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	public void Finish()
	{
		Finished = true;
		if (OnFinish != null)
		{
			OnFinish();
		}
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	public void StartFinished()
	{
		if (!Finished)
		{
			bool finished = (Activated = true);
			Finished = finished;
			if (OnStartFinished != null)
			{
				OnStartFinished();
			}
		}
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	public static bool Check(Scene scene)
	{
		return scene.Tracker.GetComponent<Switch>()?.Finished ?? false;
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	private static bool FinishedCheck(Level level)
	{
		foreach (Switch component in level.Tracker.GetComponents<Switch>())
		{
			if (!component.Activated)
			{
				return false;
			}
		}
		foreach (Switch component2 in level.Tracker.GetComponents<Switch>())
		{
			component2.Finish();
		}
		return true;
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	public static bool CheckLevelFlag(Level level)
	{
		return level.Session.GetFlag("switches_" + level.Session.Level);
	}

	[MethodImpl(MethodImplOptions.NoInlining)]
	public static void SetLevelFlag(Level level)
	{
		level.Session.SetFlag("switches_" + level.Session.Level);
	}
}
