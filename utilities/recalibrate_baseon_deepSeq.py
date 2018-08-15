#!/usr/bin/env python3

# Recalibrate confidence-level of low VAF calls with high number of PASSES
# Rename StrongEvidence/WeakEvidence/NeutralEvidence/LikelyFalsePositive into HighConf/MedConf/LowConf/Unclassified

import sys, argparse, math, gzip, os
import regex as re
from copy import copy

MY_DIR = os.path.dirname(os.path.realpath(__file__))
PRE_DIR = os.path.join(MY_DIR, os.pardir)
sys.path.append( PRE_DIR )

import genomic_file_handlers as genome

parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('-infile',   '--vcf-infile',   type=str, help='VCF in', required=True)
parser.add_argument('-outfile',  '--vcf-outfile',      type=str, help='VCF out', required=True)
parser.add_argument('-ref',      '--genome-reference',  type=str,   help='.fasta.fai file to get the contigs', required=True)

parser.add_argument('--bignova-bwa',    type=str, help='combined novaseq', )
parser.add_argument('--bignova-bowtie', type=str, help='combined novaseq', )
parser.add_argument('--bignova-novo',   type=str, help='combined novaseq', )

parser.add_argument('--spp-bwa',    type=str, help='300x', )
parser.add_argument('--spp-bowtie', type=str, help='300x', )
parser.add_argument('--spp-novo',   type=str, help='300x', )

args = parser.parse_args()

infile  = args.vcf_infile
outfile = args.vcf_outfile

nova_bwa    = args.bignova_bwa
nova_bowtie = args.bignova_bowtie
nova_novo   = args.bignova_novo

fai_file  = args.genome_reference + '.fai'
chrom_seq = genome.faiordict2contigorder(fai_file, 'fai')


def rename(line_i):
    
    line_i = re.sub( 'StrongEvidence', 'HighConf', line_i )
    line_i = re.sub( 'WeakEvidence', 'MedConf', line_i )
    line_i = re.sub( 'NeutralEvidence', 'LowConf', line_i )
    line_i = re.sub( 'LikelyFalsePositive', 'Unclassified', line_i )

    return line_i



with genome.open_textfile(infile) as fin,  open(outfile, 'w') as fout:
    
    line_i = fin.readline().rstrip()


    nova_bwa      = genome.open_textfile(nova_bwa)
    nova_bwa_line = nova_bwa.readline().rstrip()
    while nova_bwa_line.startswith('#'):
        nova_bwa_line = nova_bwa.readline().rstrip()
    
    nova_bowtie = genome.open_textfile(nova_bowtie)
    nova_bowtie_line = nova_bowtie.readline().rstrip()
    while nova_bowtie_line.startswith('#'):
        nova_bowtie_line = nova_bowtie.readline().rstrip()

    nova_novo   = genome.open_textfile(nova_novo)
    nova_novo_line = nova_novo.readline().rstrip()
    while nova_novo_line.startswith('#'):
        nova_novo_line = nova_novo.readline().rstrip()


    # Copy the headlines, but add two additional lines
    while line_i.startswith('#'):

        line_i = rename( line_i )
        fout.write( line_i + '\n' )
        line_i = fin.readline().rstrip()


    # First coordinate:
    coordinate_i = re.match( genome.pattern_chr_position, line_i )
    coordinate_i = coordinate_i.group() if coordinate_i else ''

    while line_i:
        
        line_i = rename( line_i )
        my_vcf = genome.Vcf_line( line_i )
        
        my_coordinates = [(my_vcf.chromosome, my_vcf.position)]
        
        variants_at_my_coordinate = []
        variants_at_my_coordinate.append( my_vcf )

        # As long as the "coordinate" stays the same, it will keep reading until it's different.
        while my_coordinates[0] == (my_vcf.chromosome, my_vcf.position):

            line_i = fin.readline().rstrip()
            line_i = rename( line_i )
            my_vcf = genome.Vcf_line( line_i )


            ###### VCF order checking ######
            coordinate_j = re.match( genome.pattern_chr_position, line_i )
            coordinate_j = coordinate_j.group() if coordinate_j else ''
            if genome.whoisbehind(coordinate_i, coordinate_j, chrom_seq) == 1:
                raise Exception( '{} does not seem to be properly sorted.'.format(infile) )
            coordinate_i = coordinate_j

            if my_coordinates[0] == (my_vcf.chromosome, my_vcf.position):
                variants_at_my_coordinate.append( my_vcf )     
            ###### VCF order checking ######


        ##### ##### ##### ##### ##### #####
        for my_coordinate in my_coordinates:

            ref_bases = []
            alt_bases = []
            
            for variant_i in variants_at_my_coordinate:

                ref_base = variant_i.refbase
                first_alt = variant_i.altbase.split(',')[0]

                ref_bases.append( ref_base )
                alt_bases.append( first_alt )

            # deepSeq inputs
            got_nova_bwa,    nova_bwa_variants,    nova_bwa_line    = genome.find_vcf_at_coordinate(my_coordinate, nova_bwa_line,    nova_bwa,    chrom_seq)
            got_nova_bowtie, nova_bowtie_variants, nova_bowtie_line = genome.find_vcf_at_coordinate(my_coordinate, nova_bowtie_line, nova_bowtie, chrom_seq)
            got_nova_novo,   nova_novo_variants,   nova_novo_line   = genome.find_vcf_at_coordinate(my_coordinate, nova_novo_line,   nova_novo,   chrom_seq)

            # Now, use pysam to look into the BAM file(s), variant by variant from the input:
            for ith_call, my_call in enumerate( variants_at_my_coordinate ):
                
                vcf_items = my_call.vcf_line.split('\t')
                
                tvaf      = float( my_call.get_info_value('TVAF') )
                nPASSES   = int( my_call.get_info_value('nPASSES') )
                nREJECTS  = int( my_call.get_info_value('nREJECTS') )
                
                
                if ( ('Unclassified' in my_call.filters) or ('LowConf' in my_call.filters) or ('MedConf' in my_call.filters) ) and \
                (tvaf <= 0.1 and nPASSES >= 15 and nREJECTS <= 10):

                    bwaVDP,    bwaDP    = [ int(i) for i in my_call.get_info_value('bwaDP').split(',') ]
                    bowtieVDP, bowtieDP = [ int(i) for i in my_call.get_info_value('bowtieDP').split(',') ]
                    novoVDP,   novoDP   = [ int(i) for i in my_call.get_info_value('novoDP').split(',') ]
                
                    VDP = bwaVDP + bowtieVDP + novoVDP
                    DP  = bwaDP  + bowtieDP  + novoDP
                    
                    variant_id = ( (my_call.chromosome, my_call.position), my_call.refbase, my_call.altbase )
                    ref_base   = ref_bases[ith_call]
                    first_alt  = alt_bases[ith_call]


                    # Combined NovaSeq BWA
                    if variant_id in nova_bwa_variants:

                        nova_bwa_variant_i = nova_bwa_variants[variant_id]
                        nova_bwa_tvaf = float( nova_bwa_variant_i.get_sample_value('VAF', 1) )
                        
                        if 'PASS' in nova_bwa_variant_i.filters:
                            nova_bwa_PASS    = True
                            nova_bwa_REJECT  = False
                            nova_bwa_Missing = False
                        elif 'REJECT' in nova_bwa_variant_i.filters:
                            nova_bwa_PASS    = False
                            nova_bwa_REJECT  = True
                            nova_bwa_Missing = False
                    else:
                        nova_bwa_PASS    = False
                        nova_bwa_REJECT  = False
                        nova_bwa_Missing = True


                    # Combined NovaSeq Bowtie
                    if variant_id in nova_bowtie_variants:

                        nova_bowtie_variant_i = nova_bowtie_variants[variant_id]
                        nova_bowtie_tvaf = float( nova_bwa_variant_i.get_sample_value('VAF', 1) )
                        
                        if 'PASS' in nova_bowtie_variant_i.filters:
                            nova_bowtie_PASS    = True
                            nova_bowtie_REJECT  = False
                            nova_bowtie_Missing = False
                        elif 'REJECT' in nova_bowtie_variant_i.filters:
                            nova_bowtie_PASS    = False
                            nova_bowtie_REJECT  = True
                            nova_bowtie_Missing = False
                    else:
                        nova_bowtie_PASS    = False
                        nova_bowtie_REJECT  = False
                        nova_bowtie_Missing = True


                    # Combined NovaSeq NovoAlign
                    if variant_id in nova_novo_variants:

                        nova_novo_variant_i = nova_novo_variants[variant_id]
                        nova_novo_tvaf = float( nova_bwa_variant_i.get_sample_value('VAF', 1) )
                        
                        if 'PASS' in nova_novo_variant_i.filters:
                            nova_novo_PASS    = True
                            nova_novo_REJECT  = False
                            nova_novo_Missing = False
                        elif 'REJECT' in nova_novo_variant_i.filters:
                            nova_novo_PASS    = False
                            nova_novo_REJECT  = True
                            nova_novo_Missing = False
                    else:
                        nova_novo_PASS    = False
                        nova_novo_REJECT  = False
                        nova_novo_Missing = True

                    
                    # Promote to "WeakEvidence"
                    if nova_bwa_PASS and nova_bowtie_PASS and nova_novo_PASS:
                        vcf_items[6] = re.sub('Unclassified|LowConf', 'MedConf', vcf_items[6])
                    
                    # Promote one ladder up if PASS by Burrows-Wheeler (bwa or bowtie) and NovoAlign
                    # "Missing" in 450X is worse than "missing" in 50X, so it's considered as "bad" as REJECT, i.e., two PASSES and one LowQual
                    elif ( (nova_bwa_PASS or nova_bowtie_PASS) and nova_novo_PASS ) and not (nova_bwa_REJECT or nova_bowtie_REJECT or nova_novo_REJECT or nova_bwa_Missing or nova_bowtie_Missing or nova_novo_Missing):
                        vcf_items[6] = re.sub('Unclassified', 'LowConf', vcf_items[6])
                        vcf_items[6] = re.sub('LowConf',      'MedConf', vcf_items[6])
                    
                    # Demotion
                    elif (nova_bwa_REJECT or nova_bwa_Missing) and (nova_bowtie_REJECT or nova_bowtie_Missing) and (nova_novo_REJECT or nova_novo_Missing):
                        vcf_items[6] = re.sub('MedConf', 'LowConf',     vcf_items[6])
                        vcf_items[6] = re.sub('LowConf', 'Unclassified', vcf_items[6])

                # Write
                line_out = '\t'.join(vcf_items)
                fout.write( line_out + '\n' )



    opened_files = (nova_bwa, nova_bowtie, nova_novo)
    [ opened_file.close() for opened_file in opened_files if opened_file ]
