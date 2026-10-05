# Sourced by every hpc/*.sbatch job. Check the module names once on Leonardo
# (`module avail gcc`, `module avail python`): its names often carry a compiler
# suffix, e.g. python/3.11.6--gcc--8.5.0.
module purge
module load gcc/12.2.0
module load python/3.11.7
export PATH="$HOME/bin:$PATH"          # cbmc
command -v cbmc >/dev/null || { echo "cbmc is not on PATH" >&2; exit 1; }
