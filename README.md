# bstt

## Instalation and Usage:

Using Anaconda:

conda create --name bstt

conda activate bstt

conda install numpy matplotlib scipy scikit-learn python3

See the experiments for example usage.


## File Structure

#### First level, /:

bstt.py: block sparse tensor trains

als.py: als algorithms

misc.py: helpers for bstt.py and als.py

helpers.py: this is the code for the dynamic models, e.g. fermi pasta, lennard jones etc.

#### Second level: expermiments/

The folder for each system contains a file to generate the data for each example dynamical system, a plotting file and folders containing data and figures.

1. FPUT

2. Magnetic dipole chain

3. Lennard-Jones
