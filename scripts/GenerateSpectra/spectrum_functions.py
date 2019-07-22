import os, sys, math, re, csv, glob, gzip
import numpy as np
import matplotlib.pyplot as plt
from numpy import linalg as la
from numpy import trapz
from distutils.spawn import find_executable
from pathlib import Path
from spectrum_classes import *

def intersection(lst1, lst2): 
	return set(lst1).intersection(lst2)

def find_molecules(g4_dir, path, force_field_folders):
	common_molecules = [f.path.split("/")[-1] for f in os.scandir(g4_dir) if f.is_dir()]
	for folder in force_field_folders:
		molecules        = [f.path.split("/")[-1] for f in os.scandir(path + "/" + folder) if f.is_dir()]
		common_molecules = intersection(common_molecules, molecules)
	return common_molecules

def check_or_die(filenm, die):
	if not os.path.isfile(filenm):
		print("ERROR: generating " + filenm)
		if die:
			exit(1)

def find_gmx():
	"""Find where GROMACS is installed"""
	gmx = None
	for mpi in [ "_mpi", "" ]:
		for double in [ "_d", ""]:
			gmx = find_executable("gmx" + mpi + double)
			if gmx:
				return gmx
	if not gmx:
		sys.exit("GROMACS is not installed!!!")

def run_one_nm(die, sigma, scale_factor, mdpdir, output):
	gmx = find_gmx()
	conf = "conf.gro"
	for minimize in [ "cg" ]:
		tpr  = minimize + ".tpr"
		os.system((gmx + " grompp -f " + mdpdir + "/%s.mdp -o %s -v -maxwarn 1 -c conf.gro") % (minimize, tpr))
		check_or_die(tpr, die)
		conf = ("after_%s.g96" % minimize )
		os.system((gmx + " mdrun -s %s -c %s -v") % (tpr, conf))
		check_or_die(conf, die)
	tpr = "nm.tpr"
	os.system((gmx + " grompp -c %s -f " + mdpdir + "/nm.mpd -o %s -v") % (conf, tpr))
	check_or_die(tpr, die)
	mtz = "nm.mtx"
	os.system(gmx + " mdrun -s %s -v -mtx %s" % ( tpr, mtz ))
	check_or_die(mtz, die )
	os.system(("%s nmeig -last 1000 -s %s -f %s -sigma %d > %s") % (gmx, tpr, mtz, sigma, output))

def extract_eigenfrequencies(molecule_path):
	"""Extract eigenfrequencies from GROMACS eigenfrequency file"""
	eigenfrequencies = []
	full_path = molecule_path + "/eigenfreq.xvg"
	print('reading eigenfrequencies from:', full_path)
	for line in open(full_path, "r").readlines():
		if not line == line.lstrip():
			words = line.strip().split()
			eigenfrequencies.append(float(words[1]))
	return eigenfrequencies

def extract_eigenvectors(molecule_path):
	"""Extract eigenvectors from GROMACS eigenvector file"""
	eigenvectors = []
	eigenvector  = np.empty([0,3])
	full_path    = molecule_path + "/eigenvec.trr"
	temp_txt     = molecule_path + "/eigenvec.txt"
	print('reading eigenvectors from:', full_path )
	os.system(find_gmx() + " dump -f " + full_path + " -quiet > " + temp_txt)
	for line in open(temp_txt, "r").readlines():
		if re.match(r"\s+x\[", line):
			values = re.split("[{},]",line)
			eigenvector = np.append(eigenvector, [[float(values[1]),float(values[2]),float(values[3])]], axis=0)
		elif len(eigenvector) > 0:
			eigenvectors.append(eigenvector)
			eigenvector = np.empty([0,3])
	eigenvectors.append(eigenvector)
	os.remove(molecule_path + "/eigenvec.txt")
	return eigenvectors[1:]

def extract_atomic_properties(molecule_path):
	"""Extract atomic properties from GROMACS topology file"""
	squared_masses = []
	charge_mass_factors = []
	full_path = molecule_path + "/topol.top"
	print('reading atomic properties from:', full_path)
	for line in open(full_path, "r").readlines():
		words = line.strip().split()
		if len(words) == 11:
			squared_masses.append(math.sqrt(float(words[7])))
			charge_mass_factors.append(float(words[6])/math.sqrt(float(words[7])))
	return squared_masses, charge_mass_factors

def generate_atoms(molecule_path):
	"""Initialize Atom objects and return them as a list"""
	squared_masses, charge_mass_ratios = extract_atomic_properties(molecule_path)
	atoms = []
	for i in range(len(squared_masses)):
		atom = Atom(squared_masses[i], charge_mass_ratios[i])
		atoms.append(atom)
	return atoms

def generate_normal_modes(molecule_path):
	"""Initialize NormalMode objects and return them as a list"""
	eigenfrequencies = extract_eigenfrequencies(molecule_path)
	eigenvectors     = extract_eigenvectors(molecule_path)
	normal_modes     = []
	for i in range(len(eigenfrequencies)):
		normal_mode = NormalMode(eigenfrequencies[i],eigenvectors[i])
		normal_modes.append(normal_mode)
	return normal_modes

def generate_molecule(molecule_path, linear):
	"""Initialize Molecule object"""
	atoms        = generate_atoms(molecule_path)
	normal_modes = generate_normal_modes(molecule_path)
	molecule     = Molecule(linear, atoms, normal_modes)
	for normal_mode in molecule.normal_modes():
		normal_mode.calculate_intensity(molecule.atoms())
	return molecule

def generate_cauchy_distribution(frequencies, eigenfrequency, gamma, intensity):
	"""Generate a Cauchy distribution"""
	cauchy = np.zeros(len(frequencies))
	for i in range(len(frequencies)):
		cauchy[i] = intensity*(1/math.pi)*(((1/2)*gamma)/((frequencies[i]-eigenfrequency)**2+((1/2)*gamma)**2))
	return cauchy

def generate_spectrum(input_dir, origin, molecule, linear, log, start, stop, step_size, gamma):
	print("\n<" + origin + ">")
	if log:
		path = input_dir + "/" + molecule
		return generate_spectrum_from_log(path, origin, start, stop, step_size, gamma)
	else:
		frequencies         = np.linspace(start, stop, int((stop-start)/step_size)+1)
		intensity_all_modes = np.zeros(len(frequencies))
		path = input_dir + "/" + origin + "/" + molecule
		molecule            = generate_molecule(path, linear)
		normal_modes        = molecule.normal_modes()
		for normal_mode in normal_modes:
			intensity_one_mode   = generate_cauchy_distribution(frequencies, normal_mode.eigenfrequency(), gamma, normal_mode.intensity())
			intensity_all_modes += intensity_one_mode
		return [frequencies, intensity_all_modes, origin]

def normalize_spectra(spectra):
	for i, spectrum in enumerate(spectra):
		spectra[i][1] = spectrum[1]/np.trapz(spectrum[1],spectrum[0])
	return spectra

def save_spectra_as_figure(spectra, output_dir, molecule, outformat):
	"""Write the spectrum of all normal modes of a molecule as a PNG, PDF or SVG"""
	output = output_dir + "/" + molecule + '.' + outformat

	spectra = normalize_spectra(spectra)
	score_factor = np.amax(np.correlate(spectra[0][1], spectra[0][1])).item()

	plt.figure(figsize=(18, 8))
	for spectrum in spectra:
		if not spectrum[2] == "G4":
			spectrum_score  = np.amax(np.correlate(spectra[0][1], spectrum[1])).item()/score_factor
			statistics_file = output_dir + '/' + spectrum[2] + '_statistics.csv'
			with open(statistics_file, 'a') as csvfile:
				writer = csv.writer(csvfile, delimiter=',')
				writer.writerow([molecule, spectrum_score, 0, 1])
		plt.plot(spectrum[0], spectrum[1], label=spectrum[2])
	plt.legend(loc='upper right')
	plt.title(molecule)
	plt.xlabel('Frequency, $cm^{-1}$')
	plt.ylabel('IR intensity')
	plt.yticks([])
	plt.rcParams.update({'font.size': 18})
	plt.savefig(output, format=outformat)
	plt.close()
	check_or_die(output, False)
	print('\n' + outformat.upper() + ' file saved at:', output)

def save_spectrum(g4_dir, input_dir, force_fields, molecule, output_dir,
                  linear, start, stop, step_size, gamma,
                  png, pdf, svg):
	spectra = [generate_spectrum(g4_dir, "G4", molecule, linear, True, start, stop, step_size, gamma)]
	for force_field in force_fields:
		spectra.append(generate_spectrum(input_dir, force_field, molecule, linear, False, start, stop, step_size, gamma))
	possible_formats         = ["png", "pdf", "svg"]
	desired_formats          = [ png,   pdf,   svg ]
	for i, desired_format in enumerate(desired_formats):
		if desired_format:
			selected_format = possible_formats[i]
			if Path(output_dir + "/" + molecule + '.' + selected_format).is_file():
				sys.exit('the file "' + molecule + "." + selected_format + '" already exists')
			elif not Path(output_dir).is_dir():
				sys.exit('the specified output folder "' + output_dir + '" does not exist')
			elif selected_format in [ "png", "pdf", "svg" ]:
				save_spectra_as_figure(spectra, output_dir, molecule, selected_format)

def generate_spectrum_from_log(path, origin, start, stop, step_size, gamma):
	log = None
	for found_file in glob.glob(path + '/*g4.log*'):
    		log = found_file
	if log:
		eigenfrequencies = []
		intensities      = []
		print('reading log file at:', log)
		if log.endswith(".gz"):
			lines = gzip.open(log, 'rt').readlines()
		else:
			lines = open(log, 'r').readlines()
		for line in lines:
			if "Frequencies" in line:
				values  = re.findall(r"[-+]?\d*\.\d+|\d+", line)
				for value in values:
					eigenfrequencies.append(float(value))
			elif "IR Inten" in line:
				values  = re.findall(r"[-+]?\d*\.\d+|\d+", line)
				for value in values:
					intensities.append(float(value))
	else:
        	sys.exit("The QM log file does not exist!!!")
	if eigenfrequencies and intensities:
		frequencies         = np.linspace(start, stop, int((stop-start)/step_size)+1)
		intensity_all_modes = np.zeros(len(frequencies))
		for i, eigenfrequency in enumerate(eigenfrequencies):
			intensity_one_mode   = generate_cauchy_distribution(frequencies, eigenfrequency, gamma, intensities[i])
			intensity_all_modes += intensity_one_mode
		return [frequencies, intensity_all_modes, origin]
	else:
		sys.exit("There are no frequencies and/or intensities in the QM log file!!!")