#!/usr/bin/env python3

import argparse, os, sys
from spectrum_functions import *
from pathlib import Path

pwd = os.getcwd()
parser = argparse.ArgumentParser(description='Generate the IR-spectrum for a molecule using GROMACS output files.')
parser.add_argument('-g4'        , type=str  , required=True           , help='<Required> G4 directory')
parser.add_argument('-ffd'       , type=str  , required=True           , help='<Required> Input GROMACS directory with force field directories')
parser.add_argument('-ffs'       , type=str  , required=True, nargs='+', help='<Required> List the names of the force field directories found in the input GROMACS directory' )
parser.add_argument('-o'         , type=str  , default=pwd             , help='Output spectrum directory. DEFAULT: working directory')
parser.add_argument('-min'       , type=int  , default=0               , help='Lowest frequency to visualize in spectrum. DEFAULT: 0')
parser.add_argument('-max'       , type=int  , default=4000            , help='Highest frequency to visualize in spectrum. DEFAULT: 4000')
parser.add_argument('-s'         , type=float, default=4               , help='Step size on the frequency axis. DEFAULT: 4')
parser.add_argument('-g'         , type=float, default=24              , help='Set gamma for Cauchy distribution. DEFAULT: 24')
parser.add_argument('--linear'   ,                                       help='Molecule is linear'                    , action='store_true')
parser.add_argument('--png'      ,                                       help='Generate the spectrum as a PNG'        , action='store_true')
parser.add_argument('--pdf'      ,                                       help='Generate the spectrum as a PDF'        , action='store_true')
parser.add_argument('--svg'      ,                                       help='Generate the spectrum as a SVG'        , action='store_true')

if __name__ == "__main__":
  
	args = parser.parse_args()
	
	g4_dir       = args.g4
	input_dir    = args.ffd
	force_fields = args.ffs
	output_dir   = args.o
	linear       = args.linear
	start        = args.min
	stop         = args.max
	step_size    = args.s
	gamma        = args.g
	generate_png = args.png
	generate_pdf = args.pdf
	generate_svg = args.svg
	
	molecules = find_molecules(g4_dir, input_dir, force_fields)
	for atom in ["brom", "chlor","iod"]:
		molecules = [molecule for molecule in molecules if atom not in molecule]
	print('\nThe following number of molecules were found in all listed directories and will be processed:', len(molecules))

	for force_field in force_fields:
		statistics_file = output_dir + "/" + force_field + '_statistics.csv'
		if Path(statistics_file).is_file():
				sys.exit('the file "' + force_field + '_statistics.csv" already exists')
		else:
			with open(statistics_file, 'w') as csvfile:
				writer = csv.writer(csvfile, delimiter=',')
				writer.writerow(['molecule', 'score', 'v0', 'scaling_factor'])
			check_or_die(statistics_file, True)	

	for molecule in molecules:
		print('\nNOW PROCESSING:', molecule)
		save_spectrum(g4_dir, input_dir, force_fields, molecule, output_dir,
                              linear, start, stop, step_size, gamma, 
                              generate_png, generate_pdf, generate_svg)
