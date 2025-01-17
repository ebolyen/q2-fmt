# ----------------------------------------------------------------------------
# Copyright (c) 2022, QIIME 2 development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file LICENSE, distributed with this software.
# ----------------------------------------------------------------------------

import pandas as pd
import itertools

import qiime2


def group_timepoints(
        diversity_measure: pd.Series, metadata: qiime2.Metadata,
        time_column: str, reference_column: str, subject_column: str = False,
        control_column: str = None) -> (pd.DataFrame, pd.DataFrame):

    # Data filtering
    if diversity_measure.empty:
        raise ValueError('Empty diversity measure detected.'
                         ' Please make sure your diversity measure contains data.')

    if isinstance(diversity_measure.index, pd.MultiIndex):
        is_beta = True
        ids_with_data = set(itertools.chain.from_iterable(
            diversity_measure.index))
    else:
        is_beta = False
        ids_with_data = diversity_measure.index

    metadata = metadata.filter_ids(ids_to_keep=ids_with_data)

    # TODO: refactor with a function that contains a single try/except for all columns
    try:
        time_col = metadata.get_column(time_column)
    except ValueError:
        raise ValueError('time_column provided not present within the metadata')

    if not isinstance(time_col, qiime2.NumericMetadataColumn):
        raise TypeError('Non-numeric characters detected in time_column.')
    else:
        time_col = time_col.to_series()

    # TODO: add a requirement for all samples that contain timepoint data to also contain donor data
    try:
        reference_col = metadata.get_column(reference_column)
    except ValueError:
        raise ValueError('reference_column provided not present within the metadata')
    reference_col = reference_col.to_series()
    used_references = reference_col[~time_col.isna()]

    if used_references.isna().any():
        nan_references = used_references.index[used_references.isna()]
        raise KeyError('Missing references for the associated sample data. Please make sure'
                       ' that all samples with a timepoint value have an associated reference.'
                       ' IDs where missing references were found: %s' % (tuple(nan_references),))

    if subject_column:
        try:
            subject_col = metadata.get_column(subject_column)
        except ValueError:
            raise ValueError('subject_column provided not present within the metadata')
        subject_col = subject_col.to_series()

    if control_column is not None:
        try:
            control_col = metadata.get_column(control_column)
        except ValueError:
            raise ValueError('control_column provided not present within the metadata')
        control_col = control_col.to_series()
        used_controls = control_col[~control_col.isna()]

    diversity_measure.name = 'measure'
    diversity_measure.index.name = 'id'

    # GroupDists[Ordered, Matched | Independent]
    if is_beta:
        idx = pd.MultiIndex.from_frame(
            used_references.to_frame().reset_index())
        idx.names = ['id', 'reference']
    else:
        idx = used_references.index
        idx.name = 'id'

    try:
        sliced_df = diversity_measure[idx].to_frame().reset_index().set_index('id')
    except KeyError:
        raise KeyError('Pairwise comparisons were unsuccessful. Please double check that your'
        ' chosen reference column contains values that are also present in the ID column for'
        ' the associated metadata.')

    ordinal_df = sliced_df[['measure']]
    ordinal_df['group'] = time_col
    if subject_column:
        ordinal_df['subject'] = subject_col

    # GroupDists[Unordered, Independent]
    unique_references = used_references.unique()

    if is_beta:
        try:
            ref_idx = pd.MultiIndex.from_tuples(
                itertools.combinations(unique_references, 2))
        except TypeError:
            raise TypeError('Single reference value detected. More than one unique reference must be'
                            ' provided for successful grouping.')

        ref_idx.names = ['A', 'B']

        if control_column is not None:
            grouped_md = metadata.to_dataframe().loc[used_controls.index].groupby(used_controls)
            ctrl_list = list()
            for group_id, grouped_ctrls in grouped_md:
                if len(grouped_ctrls.index) < 2:
                    continue
                ctrl_combos = list(itertools.combinations(grouped_ctrls.index, 2))
                ctrl_idx = pd.MultiIndex.from_tuples(ctrl_combos)
                ctrl_series = pd.Series(group_id, index=ctrl_idx)
                ctrl_list.append(ctrl_series)

            try:
                ctrl_series = pd.concat(ctrl_list)
            except ValueError:
                raise ValueError('One or less controls detected. When including controls in your data,'
                                 ' please include more than one for successful grouping.')

            ctrl_series.name = 'group'
            ctrl_series.index.names = ['A', 'B']

    else:
        ref_idx = list(unique_references)
        if control_column is not None:
            ctrl_series = used_controls
            ctrl_series.index.name = 'id'

    try:
        nominal_df = diversity_measure[ref_idx].to_frame().reset_index()
    except KeyError:
        raise KeyError('Pairwise comparisons were unsuccessful. Please double check that your'
        ' chosen reference column contains values that are also present in the ID column for'
        ' the associated metadata.')

    nominal_df['group'] = 'reference'

    if control_column is not None:
        ctrl_group = diversity_measure[ctrl_series.index].to_frame()
        ctrl_group['group'] = ctrl_series
        ctrl_group = ctrl_group.reset_index()
        nominal_df = pd.concat([nominal_df, ctrl_group])
        nominal_df = nominal_df.reset_index(drop=True)

    if 'A' in nominal_df.columns:
        nominal_df['id'] = nominal_df[['A', 'B']].agg('..'.join, axis=1)
        nominal_df = nominal_df[['id', 'measure', 'group', 'A', 'B']]

    nominal_df = nominal_df.set_index('id')

    return ordinal_df, nominal_df
