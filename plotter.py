import sys
import os
from warnings import warn
import logging
import functools

from numpy import *
import scipy.constants as co
import pylab
from matplotlib.colors import LogNorm
import h5py
from langevin import CylindricalLangevin
from fdtd import avg
from em import Parameters, CLASSES
import cmaps

X, Y, Z = 0, 1, 2
import functools


def main():
    logging.basicConfig(format='[%(asctime)s] %(message)s', 
                        datefmt='%a, %d %b %Y %H:%M:%S',
                        level=logging.DEBUG)

    import argparse
    parser = argparse.ArgumentParser()

    parser.add_argument("input", help="HDF5 input file")
    parser.add_argument("step", 
                        help="Step to plot ('all' and 'latest' accepted)",
                        default=None)

    parser.add_argument("vars", help="Variable(s) to plot", 
                        default=[], nargs='+')

    parser.add_argument("-o", "--output",
                        help="Output file (may contain {rid} {step} and {var})", 
                        action='store', default='{rid}_{step}_{var}.png')

    parser.add_argument("--subplots", help="Use 2 or 4 subplots", 
                        action='store', type=int, 
                        choices=[2, 4], default=None)

    parser.add_argument("--log", help="Logarithmic time scale", 
                        action='store_true', default=False)

    parser.add_argument("--show", help="Interactively show the figure", 
                        action='store_true', default=False)

    parser.add_argument("--zlim", help="Limits of the z scale (z0:z1)", 
                        action='store', default=None)

    parser.add_argument("--rlim", help="Limits of the r scale (r0:r1)", 
                        action='store', default=None)

    parser.add_argument("--clim", help="Limits of the color scale (c0:c1)", 
                        action='store', default=None)

    parser.add_argument("--cmap", help="Use a dynamic colormap", 
                        action='store', default=None)
    

    args = parser.parse_args()

    fp = h5py.File(args.input)
    all_steps = fp['steps'].keys()

    if args.step == 'all':
        steps = all_steps
    elif args.step == 'latest':
        steps = [all_steps[-1]]
    else:
        steps = [args.step]

    rid = os.path.splitext(args.input)[0]

    params = Parameters()
    params.h5_load(fp)

    for step in steps:
        sim = CLASSES[params.simulation_class].load(fp, step)
        if args.subplots == 2:
            pylab.clf()
            pylab.figure(figsize=(20, 4))
            pylab.subplots_adjust(left=0.065, right=0.98, wspace=0.07, top=0.95)
            next_plot = functools.partial(pylab.subplot, 1, 2)
        elif args.subplots == 4:
            pylab.clf()
            pylab.figure(figsize=(20, 8))
            pylab.subplots_adjust(left=0.065, right=0.98, wspace=0.07, top=0.95)
            next_plot = functools.partial(pylab.subplot, 2, 2)
        else:
            next_plot = lambda i: pylab.clf()
            pylab.figure(figsize=(20, 8))

        for i, var in enumerate(args.vars):
            next_plot(i + 1)
            f = VAR_FUNCS[var]
            v = f(sim, params)
            plot(sim, v, args, label=f.__doc__)

            if not args.show and args.subplots is None:
                ofile = args.output.format(step=step, var=var, rid=rid)
                pylab.savefig(ofile)
                logging.info("File '%s' saved" % ofile)

        if not args.show and args.subplots is not None:
            ofile = args.output.format(step=step, var='_'.join(args.vars), 
                                       rid=rid)
            pylab.savefig(ofile)
            logging.info("File '%s' saved" % ofile)


    if args.show:
        pylab.show()


VAR_FUNCS = {}
def plotting_var(func):
    VAR_FUNCS[func.__name__] = func
    return func

@plotting_var
def jr(sim, params):
    "$j_r [$\\mathdefault{A/m^2}$]"
    return sum(avg(sim.j_(R), axis=R), axis=-1)

@plotting_var
def jz(sim, params):
    "$j_z [$\\mathdefault{A/m^2}$]"
    return sum(avg(sim.j_(Z_), axis=Z_), axis=-1)

@plotting_var
def jphi(sim, params):
    return sum(avg(sim.j_(PHI), axis=PHI), axis=-1)

@plotting_var
def er(sim, params):
    "$|E_r|$ [V/m]"
    return sim.er.v

@plotting_var
def ez(sim, params):
    "$|E_z|$ [V/m]"
    return sim.ez.v

@plotting_var
def eabs(sim, params):
    "Electric field $|E|$ [V/m]"
    return sqrt(sum(sim.e**2, axis=-1))

Td = 1e-17 * co.centi**2
@plotting_var
def en(sim, params):
    "Reduced Field $E/N$ [Td]"
    mun = params.mu_N
    En = (eabs(sim, params) * co.elementary_charge / 
          (mun * sim.nu[:, :, 0] * co.electron_mass))
    En[:] = where(isfinite(En), En, 0.0)

    return En / Td


def plot(sim, var, args, label=None, reduce_res=True):
    rf = sim.rf
    zf = sim.zf
    
    if args.rlim is not None:
        rlim = [float(x) * co.kilo for x in args.rlim.split(':')]
        flt = logical_and(rf >= rlim[0], rf <= rlim[1])
        rf = rf[flt]
        var = var[flt, :]

    if args.zlim is not None:
        zlim = [float(x) * co.kilo for x in args.zlim.split(':')]
        flt = logical_and(zf >= zlim[0], zf <= zlim[1])
        zf = zf[flt]
        var = var[:, flt]

    if reduce_res:
        while len(rf) > 600 or len(zf) > 600:
            rf = rf[::2]
            zf = zf[::2]
            var = var[::2, ::2]
            warn("Reducing resolution to %dx%d" % (len(rf), len(zf)))
            
    plot_args = {}
    if args.log:
        plot_args['norm'] = LogNorm()
        
    if args.clim:
        clim = [float(x) for x in args.clim.split(':')]
        plot_args['vmin'] = clim[0]
        plot_args['vmax'] = clim[1]

    if args.cmap:
        cmap = cmaps.get_colormap(args.cmap, dynamic=False)
        vmin = plot_args.get('vmin', nanmin(var.flat))
        vmax = plot_args.get('vmax', nanmax(var.flat))

        #cmap.center = -vmin / (vmax - vmin)
        plot_args['cmap'] = cmap

    pylab.pcolor(rf / co.kilo,
                 zf / co.kilo,
                 var.T, **plot_args)
    try:
        c = pylab.colorbar()
        c.set_label(label)
    except (ValueError, AttributeError) as e:
        warn("Invalid values while plotting ez")
        
    if args.rlim is None:
        rlim = [rf[0], rf[-1]]

    if args.zlim is None:
        zlim = [zf[0], zf[-1]]

    pylab.xlim([v / co.kilo for v in rlim])
    pylab.ylim([v / co.kilo for v in zlim])

    pylab.axis('scaled')
    pylab.ylabel("z [km]")
    pylab.xlabel("r [km]")


if __name__ == '__main__':
    main()
