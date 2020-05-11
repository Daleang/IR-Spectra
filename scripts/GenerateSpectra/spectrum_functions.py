import os, sys, math, re, csv, glob, gzip, itertools
import numpy as np
import matplotlib.pyplot as plt
plt.switch_backend('agg')
plt.rcParams.update({'font.size': 11})
from numpy import linalg as la
from numpy import trapz, mean
from distutils.spawn import find_executable
from pathlib import Path
from spectrum_classes import *
from statistics import median
from scipy.stats import pearsonr, spearmanr, rankdata

def intersection(lst1, lst2): 
	return set(lst1).intersection(lst2)

def find_molecules_linear(ff_dir, ffs):
	common_molecules = []
	for ff in ffs:
		ff_molecules     = [f.path.split("/")[-1] for f in os.scandir(ff_dir + "/" + ff) if f.is_dir()]
		print("Number of molecules in %s data directory: %d" % (ff, len(ff_molecules)))
		if common_molecules == []:
			common_molecules = ff_molecules
		else:
			common_molecules = intersection(common_molecules, ff_molecules)
		linear_molecules     = ["-".join(f.path.split("/")[-1].split("-")[:-1]) for f in os.scandir(ff_dir + "/" + ff) if (f.is_dir and ("-linear" in str(f)))]
		print(linear_molecules)
		print("Number of linear molecules in %s data directory: %d" % (ff, len(linear_molecules)))
		common_molecules = intersection(common_molecules, linear_molecules)
	return list(common_molecules)

def find_molecules(exp_dir, qm_dir, qms, ff_dir, ffs):
	exp_molecules    = [os.path.splitext(os.path.basename(f.path))[0] for f in os.scandir(exp_dir) if f.is_file()]
	print("Number of molecules in %s data directory: %d" % ("experimental", len(exp_molecules)))
	common_molecules = exp_molecules
	for qm in qms:
		qm_molecules     = [f.path.split("/")[-1] for f in os.scandir(qm_dir + "/" + qm) if f.is_dir()]
		print("Number of molecules in %s data directory: %d" % (qm, len(qm_molecules)))
		common_molecules = intersection(common_molecules, qm_molecules)
	for ff in ffs:
		ff_molecules     = [f.path.split("/")[-1] for f in os.scandir(ff_dir + "/" + ff) if f.is_dir()]
		print("Number of molecules in %s data directory: %d" % (ff, len(ff_molecules)))
		common_molecules = intersection(common_molecules, ff_molecules)
	return list(common_molecules)

def find_all_molecules(exp_dir, qm_dir, qms, ff_dir, ffs):
	all_molecules = [] 
	exp_molecules    = [os.path.splitext(os.path.basename(f.path))[0] for f in os.scandir(exp_dir) if f.is_file()]
	print("Number of molecules in %s data directory: %d" % ("experimental", len(exp_molecules)))
	for molecule in exp_molecules:
		all_molecules.append([molecule, 'Experimental data'])
	for qm in qms:
		qm_molecules     = [f.path.split("/")[-1] for f in os.scandir(qm_dir + "/" + qm) if f.is_dir()]
		print("Number of molecules in %s data directory: %d" % (qm, len(qm_molecules)))
		for molecule in all_molecules:
			if (molecule[0] in qm_molecules):
				all_molecules[all_molecules.index(molecule)].append(qm)
				#print(all_molecules[all_molecules.index(molecule)], all_molecules.index(molecule))
				qm_molecules.remove(molecule[0])
		for new_molecule in qm_molecules:
			all_molecules.append([new_molecule, qm])
	for ff in ffs:
		ff_molecules     = [f.path.split("/")[-1] for f in os.scandir(ff_dir + "/" + ff) if (f.is_dir() and (os.path.isfile(f.path + "/" + "eigenvec.trr")))]
		print("Number of molecules in %s data directory: %d" % (ff, len(ff_molecules)))
		for molecule in all_molecules:
			if (molecule[0] in ff_molecules):
				all_molecules[all_molecules.index(molecule)].append(ff)
				#print(all_molecules[all_molecules.index(molecule)], all_molecules.index(molecule))
				ff_molecules.remove(molecule[0])
		for new_molecule in ff_molecules:
			all_molecules.append([new_molecule, ff])
	
	print(all_molecules)
	return all_molecules

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

def extract_eigenfrequencies(molecule_path, scaling_factor):
	"""Extract eigenfrequencies from GROMACS eigenfrequency file"""
	eigenfrequencies = []
	full_path = molecule_path + "/eigenfreq.xvg"
	#print('reading eigenfrequencies from:', full_path)
	for line in open(full_path, "r").readlines():
		if not line == line.lstrip():
			words = line.strip().split()
			eigenfrequencies.append(float(words[1]) * scaling_factor)
	return eigenfrequencies

def extract_eigenvectors(molecule_path, output_dir):
	"""Extract eigenvectors from GROMACS eigenvector file"""
	eigenvectors = []
	eigenvector  = np.empty([0,3])
	full_path    = molecule_path + "/eigenvec.trr"
	temp_txt     = output_dir + "eigenvec.txt"
	#print('reading eigenvectors from:', full_path )
	os.system(find_gmx() + " dump -f " + full_path + " -quiet > " + temp_txt)
	for line in open(temp_txt, "r").readlines():
		if re.match(r"\s+x\[", line):
			values = re.split("[{},]",line)
			eigenvector = np.append(eigenvector, [[float(values[1]),float(values[2]),float(values[3])]], axis=0)
		elif len(eigenvector) > 0:
			eigenvectors.append(eigenvector)
			eigenvector = np.empty([0,3])
	eigenvectors.append(eigenvector)
	#os.remove(temp_txt)
	return eigenvectors[1:]

def read_topol(topol):
	squared_masses = []
	charges        = []
	readatoms      = False
	for line in open(topol, "r").readlines():
		if line[0:9] == "[ atoms ]":
			readatoms = True
			continue
		if readatoms:
			if line[0] == "[":
				break
			words = line.strip().split()
			if (len(words) > 7) and not (words[0] == ";"):
				squared_masses.append([math.sqrt(float(words[7]))])
				charges.append([float(words[6])]*3)
	return np.array(squared_masses), np.array(charges)

def read_mu(mu):
	charges = []
	row     = []
	counter = 1
	for line in open(mu, "r").readlines():
		values = line.split()
		row.append(float(values[counter]))
		if counter == 3:
			charges.append(row)
			row     = []
			counter = 1
		else:
			counter += 1
	return np.array(charges)

def extract_atomic_properties(molecule_path):
	"""Extract atomic properties from GROMACS topology file"""
	topol     = molecule_path + "/topol.top"
	mu        = molecule_path + "/mu.txt"
	mu_exists = os.path.isfile(mu)
	#msg       = 'reading atomic properties from: %s' % (topol)
	#if mu_exists:
	#	msg = "%s and %s" % (msg, mu)
	#print(msg)
	squared_masses, charges = read_topol(topol)
	if mu_exists:
		charges = read_mu(mu)
		squared_masses = squared_masses[:charges.shape[0],:]            
	charge_mass_factors = np.zeros(charges.shape)
	for i in range(charges.shape[0]):
		for j in range(3):
			charge_mass_factors[i,j] = charges[i,j]/squared_masses[i]
	return squared_masses, charge_mass_factors

def generate_atoms(molecule_path):
	"""Initialize Atom objects and return them as a list"""
	squared_masses, charge_mass_ratios = extract_atomic_properties(molecule_path)
	atoms = []
	for i in range(squared_masses.shape[0]):
		atom = Atom(squared_masses[i], charge_mass_ratios[i,:])
		atoms.append(atom)
	return atoms

def generate_normal_modes(molecule_path, scaling_factor, output_dir):
	"""Initialize NormalMode objects and return them as a list"""
	eigenfrequencies = extract_eigenfrequencies(molecule_path, scaling_factor)
	eigenvectors     = extract_eigenvectors(molecule_path, output_dir)
	normal_modes     = []
	for i in range(len(eigenfrequencies)):
		normal_mode = NormalMode(eigenfrequencies[i],eigenvectors[i])
		normal_modes.append(normal_mode)
	return normal_modes

def generate_molecule(molecule_path, eigfreq_count, scaling_factor, output_dir):
	"""Initialize Molecule object"""
	atoms        = generate_atoms(molecule_path)
	normal_modes = generate_normal_modes(molecule_path, scaling_factor, output_dir)
	molecule     = Molecule(eigfreq_count, atoms, normal_modes)
	for normal_mode in molecule.normal_modes():
		normal_mode.calculate_intensity(molecule.atoms())
	return molecule

def generate_cauchy_distribution(frequencies, eigenfrequency, gamma, intensity):
	"""Generate a Cauchy distribution"""
	cauchy = np.zeros(len(frequencies))
	for i in range(len(frequencies)):
		cauchy[i] = intensity*(1/math.pi)*(((1/2)*gamma)/((frequencies[i]-eigenfrequency)**2+((1/2)*gamma)**2))
	return cauchy

def generate_spectrum(input_dir, origin, molecule, eigfreq_count, start, stop, npoints, gamma, scaling_factor, output_dir, linear):
	#print("\n<" + origin + ">")
	if linear:
		mol_name = molecule + "-linear"
		method_name = origin + "-linear"
	else:
		mol_name = molecule
		method_name = origin
	if origin in ["G4", "OEP"]:
		path = "%s/%s/%s" % (input_dir, origin, molecule)
		return generate_spectrum_from_log(path, origin, start, stop, npoints, gamma, scaling_factor)
	elif origin in ["CGenFF", "GAFF-ESP", "GAFF-BCC", "OPLS"]:
		frequencies         = np.linspace(start, stop, npoints)
		intensity_all_modes = np.zeros(len(frequencies))
		path = input_dir + "/" + origin + "/" + mol_name
		molecule            = generate_molecule(path, eigfreq_count, scaling_factor, output_dir)
		normal_modes        = molecule.normal_modes()
		eigenfrequencies    = []
		for normal_mode in normal_modes:
			intensity_one_mode   = generate_cauchy_distribution(frequencies, normal_mode.eigenfrequency(), gamma, normal_mode.intensity())
			intensity_all_modes += intensity_one_mode
			eigenfrequencies.append(normal_mode.eigenfrequency())
		return [frequencies, intensity_all_modes, np.array(eigenfrequencies), method_name]
	else:
		raise Exception("%s is not a supported format. Please add it to code!" % (origin))

def normalize_spectra(spectra):
	for i, spectrum in enumerate(spectra):
		spectra[i][1] = (spectrum[1] - min(spectrum[1]))/np.trapz((spectrum[1] - min(spectrum[1])),spectrum[0])
	return spectra

def cosine_distance(spectrum1, spectrum2):
	return (spectrum1.dot(spectrum2))/(math.sqrt(spectrum1.dot(spectrum1))*math.sqrt(spectrum2.dot(spectrum2)))

def rmsd(eigfreqs1, eigfreqs2):
	return math.sqrt(sum((eigfreqs1-eigfreqs2)**2)/len(eigfreqs1))

def cross_compare(molecules, all_spectra, methods, output_dir):
	out_stats = open(output_dir + '/CSV/matching.txt', 'w')
	for method in methods:
		out_pearson = open(output_dir + '/CSV/' + method + '_pearson.csv', 'w')
		out_spearman = open(output_dir + '/CSV/' + method + '_spearman.csv', 'w')
		write_pearson = csv.writer(out_pearson, delimiter ='|')
		write_spearman = csv.writer(out_spearman, delimiter ='|')
		write_pearson.writerow(['Theory/Exp.'] + molecules)
		write_spearman.writerow(['Theory/Exp.'] + molecules)
		pearsoncorrect = 0
		spearmancorrect = 0
		pearsonranks = []
		spearmanranks = []
		for molecule1 in molecules:
			for spectrum in all_spectra[molecule1]:
				if spectrum[3] == method:
					pearsons = []
					spearmans = []
					for molecule2 in molecules:
						if len(all_spectra[molecule2][0][1]) == len(spectrum[1]):
							pearsons.append(pearsonr(all_spectra[molecule2][0][1], spectrum[1])[0])
							spearmans.append(spearmanr(all_spectra[molecule2][0][1], spectrum[1])[0])
						else:
							pearsons.append(0)
							spearmans.append(0)
					if molecules[pearsons.index(max(pearsons))] == molecule1:
						pearsoncorrect += 1
					if molecules[spearmans.index(max(spearmans))] == molecule1:
						spearmancorrect += 1
					pearsonranks.append(len(pearsons) + 1 - rankdata(pearsons)[pearsons.index(pearsonr(all_spectra[molecule1][0][1], spectrum[1])[0])].astype(int))
					spearmanranks.append(len(spearmans) + 1 - rankdata(spearmans)[spearmans.index(spearmanr(all_spectra[molecule1][0][1], spectrum[1])[0])].astype(int))
					pearsons.append(molecules[pearsons.index(max(pearsons))])
					spearmans.append(molecules[spearmans.index(max(spearmans))])
					pearsons.insert(0, molecule1)
					spearmans.insert(0, molecule1)
					write_pearson.writerow(pearsons)
					write_spearman.writerow(spearmans)
		out_stats.write("%s vs. Exp. Pearson correct:  %d of %d, rank average: %.2f rank median: %d \n" % (method, pearsoncorrect, len(molecules), mean(pearsonranks), median(pearsonranks)))
		out_stats.write("%s vs. Exp. Spearman correct: %d of %d, rank average: %.2f rank median: %d \n" % (method, spearmancorrect, len(molecules), mean(spearmanranks), median(spearmanranks)))

		out_pearson_inv = open(output_dir + '/CSV/' + method + '_pearson_inv.csv', 'w')
		out_spearman_inv = open(output_dir + '/CSV/' + method + '_spearman_inv.csv', 'w')
		write_pearson_inv = csv.writer(out_pearson_inv, delimiter ='|')
		write_spearman_inv = csv.writer(out_spearman_inv, delimiter ='|')
		write_pearson_inv.writerow(['Exp./Theory'] + molecules)
		write_spearman_inv.writerow(['Exp./Theory'] + molecules)
		pearsoncorrect_inv = 0
		spearmancorrect_inv = 0
		pearsonranks = []
		spearmanranks = []
		for molecule1 in molecules:
			pearsons = []
			spearmans = []
			for molecule2 in molecules:
				for spectrum in all_spectra[molecule2]:
					if spectrum[3] == method:
						if len(all_spectra[molecule1][0][1]) == len(spectrum[1]):
							pearsons.append(pearsonr(all_spectra[molecule1][0][1], spectrum[1])[0])
							spearmans.append(spearmanr(all_spectra[molecule1][0][1], spectrum[1])[0])
						else:
							pearsons.append(0)
							spearmans.append(0)
			if molecules[pearsons.index(max(pearsons))] == molecule1:
				pearsoncorrect_inv += 1
			if molecules[spearmans.index(max(spearmans))] == molecule1:
				spearmancorrect_inv += 1
			for spectrum in all_spectra[molecule1]:
				if spectrum[3] == method:
					pearsonranks.append(len(pearsons) + 1 - rankdata(pearsons)[pearsons.index(pearsonr(all_spectra[molecule1][0][1], spectrum[1])[0])].astype(int))
					spearmanranks.append(len(spearmans) + 1 - rankdata(spearmans)[spearmans.index(spearmanr(all_spectra[molecule1][0][1], spectrum[1])[0])].astype(int))
			pearsons.append(molecules[pearsons.index(max(pearsons))])
			spearmans.append(molecules[spearmans.index(max(spearmans))])
			pearsons.insert(0, molecule1)
			spearmans.insert(0, molecule1)
			write_pearson_inv.writerow(pearsons)
			write_spearman_inv.writerow(spearmans)
		out_stats.write("Exp. vs. %s Pearson correct:  %d of %d, rank average: %.2f rank median: %d \n" % (method, pearsoncorrect_inv, len(molecules), mean(pearsonranks), median(pearsonranks)))
		out_stats.write("Exp. vs. %s Spearman correct: %d of %d, rank average: %.2f rank median: %d \n\n" % (method, spearmancorrect_inv, len(molecules), mean(spearmanranks), median(spearmanranks)))

def exp_intracorr(molecules, all_spectra, output_dir):
	out_pearson = open(output_dir + '/CSV/exp_intra_pearson.csv', 'w')
	out_spearman = open(output_dir + '/CSV/exp_intra_spearman.csv', 'w')
	write_pearson = csv.writer(out_pearson, delimiter ='|')
	write_spearman = csv.writer(out_spearman, delimiter ='|')
	write_pearson.writerow(['Exp./Exp.'] + molecules)
	write_spearman.writerow(['Exp./Exp.'] + molecules)
	for molecule1 in molecules:
		pearsons = []
		spearmans = []
		for molecule2 in molecules:
			if len(all_spectra[molecule2][0][1]) == len(all_spectra[molecule1][0][1]):
				pearsons.append(pearsonr(all_spectra[molecule2][0][1], all_spectra[molecule1][0][1])[0])
				spearmans.append(spearmanr(all_spectra[molecule2][0][1], all_spectra[molecule1][0][1])[0])
			else:
				pearsons.append(0)
				spearmans.append(0)
		pearsons.insert(0, molecule1)
		spearmans.insert(0, molecule1)
		write_pearson.writerow(pearsons)
		write_spearman.writerow(spearmans)


def save_spectra_as_figure(spectra, output_dir, molecule, outformat):
	"""Write the spectrum of all normal modes of a molecule as a PNG, PDF or SVG"""
	outformat_dir = output_dir + "/" + outformat.upper()
	if not Path(outformat_dir).is_dir():
		os.system("mkdir " + outformat_dir)
	output = outformat_dir + "/" + molecule + '.' + outformat
	output2 = outformat_dir + "/" + molecule + '2.' + outformat

	#colors     = itertools.cycle(('k', 'r', 'b'))
	colors     = {
			'Experimental data': 'k', 
			'G4': '#1b9e77', 
			'OEP': '#d95f02', 
			'CGenFF': '#7570b3', 
			'GAFF-BCC': '#e7298a', 
			'GAFF-ESP': '#66a61e', 
			'OPLS': '#e6ab02'
	}
	linestyles = {
			'Experimental data': '-', 
			'G4': '--', 
			'OEP': '-.', 
			'CGenFF': ':', 
			'GAFF-BCC': (0, (4, 1, 1, 1, 1, 1)), 
			'GAFF-ESP': (0, (4, 4)), 
			'OPLS': (0, (4, 2, 1, 1, 1, 1, 1, 2)) 
	}
	plt.figure(figsize=(10.8, 6.75))
	plt.rc('font', size=16)
	for spectrum in spectra:
		#if not spectrum[3] == "Experimental data":
			#cos_score       = cosine_distance(spectra[0][1], spectrum[1])
			#pearson_score   = pearsonr(spectra[0][1], spectrum[1])[0]
			#spearman_score  = spearmanr(spectra[0][1], spectrum[1])[0]
			#statistics_file = output_dir + '/CSV/SINGLE/' + spectrum[3] + '_statistics.csv'
			#with open(statistics_file, 'a') as csvfile:
			 	#writer = csv.writer(csvfile, delimiter='|')
			 	#writer.writerow([molecule, cos_score, pearson_score, spearman_score])
		figlabel = spectrum[3]
		intensities = spectrum[1]
		if spectrum[3] == "OEP":
			figlabel = "B3LYP/aug-cc-pVTZ"
			#intensities = -1 * spectrum[1]
		elif spectrum[3] == "G4":
			figlabel = "B3LYP/6-31G(2df,p)"
			#intensities = -1 * spectrum[1]
		#elif spectrum[3] == "Experimental data":
			#intensities = -1 * spectrum[1]
		plt.plot(spectrum[0], intensities, color=colors[spectrum[3]], linestyle=linestyles[spectrum[3]], label=figlabel)
	plt.xlabel('Wavenumber, $cm^{-1}$', size = 24)
	plt.ylabel('IR intensity', size = 24)
	plt.yticks([])
	plt.savefig(output, format=outformat, bbox_inches='tight')
	plt.legend(loc='upper right')
	plt.savefig(output2, format=outformat, bbox_inches='tight')
	plt.close()
	check_or_die(output, False)
	print('\n' + outformat.upper() + ' file saved at:', output)
	
	# save spectral data
	outdata_dir = output_dir + "/spectral_data"
	if not Path(outdata_dir).is_dir():
		os.system("mkdir " + outdata_dir)
	outdata_file = outdata_dir + "/" + molecule + ".csv"
	with open(outdata_file, 'w') as csvfile:
		writer = csv.writer(csvfile, delimiter='|')
		line = ['Frequency']
		for spectrum in spectra:
			line.append(spectrum[3])
		writer.writerow(line)
		for freqn in range(len(spectra[0][0])):
			line = []
			line.append(spectra[0][0][freqn])
			for spectrum in spectra:
				line.append(spectrum[1][freqn])
			writer.writerow(line)

def save_statistics(spectra, output_dir):
	for spectrum in spectra:
		if not spectrum[3] == "Experimental data":
			cos_score       = cosine_distance(spectra[0][1], spectrum[1])
			pearson_score   = pearsonr(spectra[0][1], spectrum[1])[0]
			spearman_score  = spearmanr(spectra[0][1], spectrum[1])[0]
			statistics_file = output_dir + '/CSV/SINGLE/' + spectrum[3] + '_statistics.csv'
			with open(statistics_file, 'a') as csvfile:
			 	writer = csv.writer(csvfile, delimiter='|')
			 	writer.writerow([molecule, cos_score, pearson_score, spearman_score])

def save_spectrum(exp_dir, qm_dir, qms, ff_dir, ffs, molecule, output_dir, start, stop, npoints, gamma, png, pdf, svg):
	spectra = []
	
	exp_path = exp_dir + '/' + molecule + '.jdx'
	if Path(exp_path).exists():
		exp_spectrum, start_exp, stop_exp, deltax = read_exp_data(exp_dir, molecule)
		if start_exp > start:
			start = start_exp
		if stop_exp < stop:
			stop = stop_exp
		exp_spectrum[1] = exp_spectrum[1][np.logical_and((np.array(exp_spectrum[0]) >= start), (np.array(exp_spectrum[0]) <= stop))]
		#npoints = int(np.round(((stop - start) / deltax) + 1))
		npoints = int(len(exp_spectrum[1]))
		exp_spectrum[0] = np.linspace(start, stop, npoints)
		spectra.append(exp_spectrum)
	
	method_factors = {"G4": 0.955, "OEP": 0.959}
	#method_factors = {"G4": 0.965, "OEP": 0.968}
	for qm in qms:
		scaling_factor = method_factors.get(qm, 1.0)
		spectra.append(generate_spectrum(qm_dir, qm, molecule, None, start, stop, npoints, gamma, scaling_factor, output_dir, False))
	
	eigfreq_count = 0
	#len(spectra[1][2])
	for ff in ffs:
		scaling_factor = method_factors.get(ff, 1.0)
		spectra.append(generate_spectrum(ff_dir, ff, molecule, eigfreq_count, start, stop, npoints, gamma, scaling_factor, output_dir, False))

	spectra = normalize_spectra(spectra)
	
	#save_statistics(spectra, output_dir)

	possible_formats         = ["png", "pdf", "svg"]
	desired_formats          = [ png,   pdf,   svg ]
	for i, desired_format in enumerate(desired_formats):
		if desired_format:
			selected_format = possible_formats[i]
			if selected_format in [ "png", "pdf", "svg" ]:
				save_spectra_as_figure(spectra, output_dir, molecule, selected_format)
	return spectra

def save_spectrum_linear(exp_dir, ff_dir, ffs, molecule, output_dir, start, stop, npoints, gamma, png, pdf, svg):
	spectra = []
	
	exp_path = exp_dir + '/' + molecule + '.jdx'
	if Path(exp_path).exists():
		exp_spectrum, start_exp, stop_exp, deltax = read_exp_data(exp_dir, molecule)
		if start_exp > start:
			start = start_exp
		if stop_exp < stop:
			stop = stop_exp
		exp_spectrum[1] = exp_spectrum[1][np.logical_and((np.array(exp_spectrum[0]) >= start), (np.array(exp_spectrum[0]) <= stop))]
		#npoints = int(np.round(((stop - start) / deltax) + 1))
		npoints = int(len(exp_spectrum[1]))
		exp_spectrum[0] = np.linspace(start, stop, npoints)
		spectra.append(exp_spectrum)
	
	eigfreq_count = 0
	for ff in ffs:
		scaling_factor = 1.0
		spectra.append(generate_spectrum(ff_dir, ff, molecule, eigfreq_count, start, stop, npoints, gamma, scaling_factor, output_dir, True))
		spectra.append(generate_spectrum(ff_dir, ff, molecule, eigfreq_count, start, stop, npoints, gamma, scaling_factor, output_dir, False))

	spectra = normalize_spectra(spectra)
	
	for spectrum in spectra:
		if not spectrum[3] == "Experimental data":
			cos_score       = cosine_distance(spectra[0][1], spectrum[1])
			pearson_score   = pearsonr(spectra[0][1], spectrum[1])[0]
			spearman_score  = spearmanr(spectra[0][1], spectrum[1])[0]
			statistics_file = output_dir + '/CSV/SINGLE/' + spectrum[3] + '_statistics.csv'
			with open(statistics_file, 'a') as csvfile:
			 	writer = csv.writer(csvfile, delimiter='|')
			 	writer.writerow([molecule, cos_score, pearson_score, spearman_score])

	possible_formats         = ["png", "pdf", "svg"]
	desired_formats          = [ png,   pdf,   svg ]
	for i, desired_format in enumerate(desired_formats):
		if desired_format:
			selected_format = possible_formats[i]
			if selected_format in [ "png", "pdf", "svg" ]:
				save_spectra_as_figure(spectra, output_dir, molecule, selected_format)
	return spectra

def cmp_spectra(exp_dir, md_dir, n_pool, ff_dir, ffs, molecule, argons, output_dir, start, stop, npoints, gamma, png, pdf, svg):
	spectra = []
	method_factors = {"G4": 0.965, "OEP": 0.968}

	for n_argon in argons:
		mdspec_path = md_dir + '/' + molecule + '/spectrum-na' + str(n_argon) + '-len100-temp350/IR-spectrum.xvg'
		lines = open(mdspec_path, 'r').readlines()
		frequencies = []
		intensities = []
		for line in lines:
			frequency = float(line.split()[0])
			#if (frequency >= start) and (frequency <= stop): 
			frequencies.append(frequency)
			intensities.append(float(line.split()[1]))
		#smooth and downsample spectrum
		freqs_flat = np.convolve(frequencies, np.ones((n_pool, ))/n_pool, mode='valid')[::n_pool]
		intens_flat = np.convolve(intensities, np.ones((n_pool, ))/n_pool, mode='valid')[::n_pool]
		#select range for ouput
		mask = np.multiply((freqs_flat >= start),  (freqs_flat <= stop))
		frequencies = freqs_flat[mask]
		intensities = intens_flat[mask]
		spectrum = [frequencies, np.array(intensities), None, "n_Ar = " + str(n_argon)]
		spectra.append(spectrum)
	npoints = len(frequencies)
	start = min(frequencies)
	stop = max(frequencies)

	#exp_path = exp_dir + '/' + molecule + '.jdx'
	#if Path(exp_path).exists():
		#exp_spectrum, start_exp, stop_exp, deltax = read_exp_data(exp_dir, molecule)
		#if start_exp > start:
			#start = start_exp
		#if stop_exp < stop:
			#stop = stop_exp
		#exp_spectrum[1] = exp_spectrum[1][np.logical_and((np.array(exp_spectrum[0]) >= start), (np.array(exp_spectrum[0]) <= stop))]
		#npoints = int(len(exp_spectrum[1]))
		#exp_spectrum[0] = np.linspace(start, stop, npoints)
		#spectra.append(exp_spectrum)
	
	eigfreq_count = 0
	for ff in ffs:
		scaling_factor = method_factors.get(ff, 1.0)
		spectra.append(generate_spectrum(ff_dir, ff, molecule, eigfreq_count, start, stop, npoints, gamma, scaling_factor, output_dir, False))
	
	spectra = normalize_spectra(spectra)

	oldspecs = []
	pearsons = [molecule + ' Pearson']
	spearmans = [molecule + ' Spearman']
	for spec1 in spectra:
		oldspecs.append(spec1[3])
		for spec2 in spectra:
			if not (spec2[3] in oldspecs):
				pearsons.append(pearsonr(spec1[1],spec2[1])[0])
				spearmans.append(spearmanr(spec1[1],spec2[1])[0])

	statistics_file = output_dir + '/CSV/cmp_statistics.csv'
	with open(statistics_file, 'a') as csvfile:
		writer = csv.writer(csvfile, delimiter ='|')
		writer.writerow(pearsons)
		writer.writerow(spearmans)

	spectra[-1][1] *= -1

	possible_formats         = ["png", "pdf", "svg"]
	desired_formats          = [ png,   pdf,   svg ]
	for i, desired_format in enumerate(desired_formats):
		if desired_format:
			selected_format = possible_formats[i]
			if selected_format in [ "png", "pdf", "svg" ]:
				save_spectra_as_figure(spectra, output_dir, molecule, selected_format)

	return spectra

def generate_spectrum_from_log(path, origin, start, stop, npoints, gamma, scaling_factor):
	log = None
	for found_file in glob.glob('%s/*%s.log*' % (path, origin.lower())):
    		log = found_file
	if log:
		eigenfrequencies = []
		intensities      = []
		#print('reading log file at:', log)
		if log.endswith(".gz"):
			lines = gzip.open(log, 'rt').readlines()
		else:
			lines = open(log, 'r').readlines()
		for line in lines:
			if "Frequencies" in line:
				values  = re.findall(r"[-+]?\d*\.\d+|\d+", line)
				for value in values:
					eigenfrequencies.append(float(value) * scaling_factor)
			elif "IR Inten" in line:
				values  = re.findall(r"[-+]?\d*\.\d+|\d+", line)
				for value in values:
					intensities.append(float(value))
	else:
        	sys.exit("The QM log file does not exist!!!")
	if eigenfrequencies and intensities:
		frequencies         = np.linspace(start, stop, npoints)
		intensity_all_modes = np.zeros(len(frequencies))
		for i, eigenfrequency in enumerate(eigenfrequencies):
			intensity_one_mode   = generate_cauchy_distribution(frequencies, eigenfrequency, gamma, intensities[i])
			intensity_all_modes += intensity_one_mode
		return [frequencies, intensity_all_modes, np.array(eigenfrequencies), origin]
	else:
		sys.exit("There are no frequencies and/or intensities in the QM log file!!!")

def read_exp_data(exp_dir, molecule):
	full_path = exp_dir + '/' + molecule + '.jdx'
	exp = None
	for found_file in glob.glob(full_path):
		exp = found_file
	if exp:
		intensities = []
		#print('\n<EXP>\nreading experimental data file at:', exp)
		lines = open(exp, 'r').readlines()
		for line in lines:
			words  = line.split('=')
			if len(words) == 2:
				if "MAXX" in words[0]:
					stop = float(words[1])
				elif "MINX" in words[0]:
					start = float(words[1])
				elif "NPOINTS" in words[0]:
					npoints = int(words[1])
				elif "DELTAX" in words[0]:
					deltax = float(words[1])
			else:
				words = line.split()
				if words[0].replace('.','',1).isdigit():
					for word in words[1:]:
						intensities.append(float(word))
		frequencies = np.linspace(start, stop, npoints)
		return [frequencies, np.array(intensities), None, "Experimental data"], start, stop, deltax
	else:
		sys.exit("The experimental data file does not exist!!!")
